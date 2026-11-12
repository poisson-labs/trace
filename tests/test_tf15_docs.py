"""TF15-S40 to TF15-S42: the README, the integration pages and the figures say what the statistics
of section 9.7 print (ST10: "TF15 builds the ruled fixes and rewrites the README's verdict list").

- TF15-S40: every marked block of the README holds when its commands are run, in README order, in
  a folder laid out as a clone (the pages' rule, TF3-32, applied to the README): an output block is
  the whole of what the command printed, an excerpt a run of its lines, each with its exit code.
  Today's README passes it; the statistics fixes change what its where, compare and fix-check
  blocks print, so the README's blocks are regenerated with them.
- TF15-S41: no page shows a method or a number the fixes retire: Sato's interval, Schoenfeld's
  limit, Kaplan-Meier and Greenwood's band, the per-input rise column, compare's 1.457, and the
  median that counted finished tries ("median step: 50"); the figures included.
- TF15-S42: the README's verdict list does not read *no significant difference* as "no difference
  was seen" nor *too small to tell* as a statement about what happened ("whatever happened").
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import FIXTURES
from tf3_support import REPO, holds_block, run_page, shims

DOCS = [REPO / "README.md", *sorted((REPO / "docs" / "integrations").glob("*.md")), *sorted((REPO / "docs" / "figures").glob("*.svg"))]


def test_tf15_s40_every_marked_block_of_the_readme_holds(tmp_path: Path) -> None:
    """The figures the README's where block writes (--svg docs/figures/... --force) are written
    in the copy and must equal the committed ones, so the README shows the curve where prints."""
    root = tmp_path / "clone"
    shutil.copytree(FIXTURES, root / "tests" / "fixtures")
    (root / "docs" / "figures").mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    checked = run_page(REPO / "README.md", root, home, shims(tmp_path / "bin"))
    assert len(checked) >= 20, len(checked)
    for c in checked:
        assert holds_block(c), f"README.md:{c.block.line}: {c.command} -> exit {c.code}\n--- block\n{c.block.body}\n--- printed\n{c.printed}"
    written = sorted((root / "docs" / "figures").glob("*.svg"))
    assert written, "the README writes no figure"
    for svg in written:
        assert svg.read_bytes() == (REPO / "docs" / "figures" / svg.name).read_bytes(), svg.name


# compare's 1.457 as the limit and the ceiling it offered; its per-kind column is left to the
# pending yes/no on that column (test_tf15_per_kind_limit)
RETIRED = (
    "Sato", "Schoenfeld", "Kaplan", "Greenwood", "could not have detected a rise below",
    "hazard ratio below 1.457", "--max-mde-hr 1.457", "median step:",
)


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_tf15_s41_no_page_shows_a_retired_method_or_number(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for word in RETIRED:
        assert word not in text, f"{path.relative_to(REPO)}: {word}"


def test_tf15_s42_the_verdict_list_claims_no_more_than_the_statistics() -> None:
    text = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
    for phrase in ("no difference was seen", "whatever happened", "could not have seen a drop"):
        assert phrase not in text, phrase
    for verdict in ("*different*", "*no significant difference*", "*too small to tell*"):
        assert f"- {verdict}:" in text, verdict
    # ST2: no significant difference is the range lying inside the size asked, either way
    nsd = text.split("- *no significant difference*:", 1)[1].split("- *too small to tell*:", 1)[0]
    assert "inside" in nsd and "--max-mde" in nsd, nsd


def test_tf15_s45_the_rebuilt_files_are_0_1_0a1() -> None:
    """S8 (ruled 2026-10-20): two different files should not carry one version. Moved from
    0.1.0rc2 to 0.1.0a1 by the pre-release cut (2026-11-11), the quiet alpha on PyPI."""
    import tomllib

    import poisson_trace

    assert poisson_trace.__version__ == "0.1.0a1"
    assert tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] == "0.1.0a1"
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "0.1.0a1" in readme and "0.1.0rc2" not in readme and "0.1.0rc1" not in readme
    assert "## 0.1.0a1" in (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
