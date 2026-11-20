"""TF15-S41 and TF15-S42: the README, the integration pages and the figures say what the
statistics print (the methods docs/how-it-decides.md describes), and the README's verdict list.

- TF15-S41: no page shows a method or a number the statistics no longer use: Sato's interval,
  Schoenfeld's limit, Kaplan-Meier and Greenwood's band, the per-input rise column, compare's 1.457,
  and the median that counted finished tries ("median step: 50"); the figures included.
- TF15-S42: the README's verdict list does not read *no significant difference* as "no difference
  was seen" nor *too small to tell* as a statement about what happened ("whatever happened").

The README's marked blocks are run by ``test_docs_blocks.py`` (TF5-14), which also holds that the
figures the README writes equal the committed ones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from junit_table_support import REPO

DOCS = [REPO / "README.md", *sorted((REPO / "docs" / "integrations").glob("*.md")), *sorted((REPO / "docs" / "figures").glob("*.svg"))]


# compare's 1.457 as the limit and the ceiling it offered; its per-kind column is held by
# test_summaries_per_kind_limit
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
    # no significant difference is the range lying inside the size asked, either way
    nsd = text.split("- *no significant difference*:", 1)[1].split("- *too small to tell*:", 1)[0]
    assert "inside" in nsd and "--max-mde" in nsd, nsd


def test_tf15_s45_the_rebuilt_files_are_0_1_0a1() -> None:
    """Two different files should not carry one version: the release is 0.1.0a1 throughout,
    and no page still names 0.1.0rc1 or 0.1.0rc2."""
    import tomllib

    import poisson_trace

    assert poisson_trace.__version__ == "0.1.0a1"
    assert tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] == "0.1.0a1"
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "0.1.0a1" in readme and "0.1.0rc2" not in readme and "0.1.0rc1" not in readme
    assert "## 0.1.0a1" in (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
