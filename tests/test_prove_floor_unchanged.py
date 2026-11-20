"""PF-96: no page shows one Prove as the version Trace reads, and the docs checker holds
``doctor``'s Prove line on any version.

- PF-96: the setup page shows ``doctor``'s Prove line with the version written ``…``; the checker
  holds that line on any Prove at or above the floor and on no other wording; and no page holds
  one Prove's version in that line, or the exact pin.
"""

from __future__ import annotations

import re

from prove_floor_pins import REPO
from pin_support import FORMAT_1_0, OR_LATER, RECORDED


# ---------- PF-96 ----------


def test_pf_96_the_checker_holds_that_line_on_any_version() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("docs_check_pf", REPO / "tools" / "docs_check.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules["docs_check_pf"] = module
    try:
        spec.loader.exec_module(module)
        shown = f"  prove     poisson-prove … (Trace reads version {OR_LATER})"
        for version in (RECORDED, "0.4.1", "1.0.0", "0.10.2"):
            assert module.line_holds(shown, f"  prove     poisson-prove {version} (Trace reads version {OR_LATER})", True), version
        assert not module.line_holds(shown, f"  prove     poisson-prove {RECORDED} (the version Trace reads)", True)
        assert not module.line_holds(shown, f"  prove     poisson-prove {RECORDED} is installed, and Trace reads version {OR_LATER}", True)
        assert not module.line_holds(shown, f"  prove     poisson-prove {RECORDED} (Trace reads version {OR_LATER})", False)
    finally:
        del sys.modules["docs_check_pf"]


def test_pf_96_no_page_shows_one_prove_as_the_version_trace_reads() -> None:
    pages = [REPO / "README.md", REPO / "CONTRIBUTING.md", *sorted((REPO / "docs").rglob("*.md"))]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "(the version Trace reads)" not in text, page.name
        assert not re.search(r"poisson-prove \d+\.\d+\.\d+ \(Trace reads", text), f"{page.name} holds one Prove's version in doctor's line"
        assert f"poisson-prove=={FORMAT_1_0}" not in text and f"poisson-prove {FORMAT_1_0}" not in text, page.name
