"""TR73 on a design the frozen tests do not reach: a few inputs repeat, and all of their repeats
sit on one version.

The frozen tests pin *an input repeats when either version holds two or more of its runs* on
designs where every input repeats, and pin the few-repeat block on designs that repeat on the
old version or on both. A build that counted repeats on the old version alone would print κ for
a design whose few repeats are all on the new version, and pass every frozen test; a build
counting the new version alone is the mirror. Here two of six inputs repeat, on the new
version alone and then on the old alone, and the block is TR73's two lines with *2 of 6*
either way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import Row, build_store
from fixcheck_support import fix_check

FEW = (
    "consistency cannot be measured with {k} of {m} inputs run more than once on a version: it "
    "takes at least half the inputs run two or more times on a version to see whether a failure "
    "repeats"
)


def _rows(outcomes_by_input: list[list[str]]) -> list[Row]:
    return [
        Row({"input": i}, o, None, replicate_index=j, seed=j)
        for i, outcomes in enumerate(outcomes_by_input)
        for j, o in enumerate(outcomes)
    ]


def _block(out: str) -> list[str]:
    start = out.index("## Consistency\n")
    end = out.index("\n## ", start + 3)
    return [line for line in out[start:end].splitlines()[1:] if line.strip()]


@pytest.mark.parametrize("version", ["new", "old"])
def test_tr73_few_inputs_repeating_on_one_version_alone_print_no_kappa(
    tmp_path: Path, version: str
) -> None:
    """Six inputs: the first two run twice on one version and once on the other, the rest once
    on each. Two of six repeat, whichever version holds the repeats."""
    once = [["fail"], ["ok"], ["fail"], ["ok"], ["fail"], ["ok"]]
    twice = [["fail", "ok"], ["ok", "fail"], *once[2:]]
    old, new = (once, twice) if version == "new" else (twice, once)
    build_store(tmp_path, "a", _rows(old))
    build_store(tmp_path, "b", _rows(new))
    argv = ("--inputs", "all", "--max-mde", "0.5")
    r = fix_check(tmp_path, "a", "b", ("fail",), *argv)
    assert r.code == 0, r.text
    d = fix_check(tmp_path, "a", "b", ("fail",), *argv, "--json").json()
    assert d["inputs"]["compared"] == 6
    c = d["consistency"]
    assert _block(r.out) == [f"failure share {c['failure_share']:.3f}", FEW.format(k=2, m=6)]
    assert c["fails_again"] is None and c["kappa"] is None, c
