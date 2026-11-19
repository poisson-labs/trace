"""TF5-3: two rules of what the commands print that the docs pair set.

**TF5-3** The top help lists the verbs in one order, and the refusal of the bare command lists them
in that order (ruled 2026-11-13, DOC-33). And no text the package can print names
``proofload-runs``, the store folder Prove had before it was published.

TF5-1, TF5-2, the rest of TF5-3 and TF5-4 to TF5-8 (every command, the pages, the app, ``init``,
``doctor`` and the setup skill as main 2ff191b gave them, each help and refusal as that main's
text with one named change, and the tests of those pins) were cut on the rulings of 2026-11-18
(AR-1, AR-3): ``test_pl_unchanged.py`` (PL-51 to PL-55) holds each of those outputs at today's
bytes.
"""

from __future__ import annotations

import re
from pathlib import Path

from tf5_pins import CHANGED, NO_VERB, NO_VERB_MAIN, OLD_STORE, ran_case
from tf5_support import VERBS


# ---------- TF5-3 ----------


def test_tf5_3_that_order_is_the_top_help_s(tmp_path: Path) -> None:
    (_, out, _), = ran_case(tmp_path, *CHANGED["help: top"])
    lines = out.splitlines()
    listed = [line.split()[0] for line in lines[lines.index("verbs:") + 2:lines.index("examples:")] if re.match(r"^    \S", line)]
    assert tuple(listed) == VERBS
    assert NO_VERB.endswith(" " + ", ".join(VERBS[:-1]) + " and " + VERBS[-1])
    assert sorted(re.split(r", | and ", NO_VERB_MAIN.split(" are ")[1])) == sorted(VERBS) and NO_VERB_MAIN != NO_VERB, "the same twelve verbs"


def test_tf5_3_no_text_the_package_can_print_names_the_old_folder() -> None:
    from tf3_support import src_files

    hits = [(path.name, n) for path in src_files() for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if OLD_STORE in line]
    assert hits == []
