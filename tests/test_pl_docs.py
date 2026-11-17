"""PL-60 and PL-61: the config's page says how a team names its labels' kinds.

- PL-60: ``docs/config.md`` gains lines and loses none, every one inside its ``[taxonomy]``
  part: they name the setting ``labels`` and the table ``[taxonomy.labels]``, show it in a
  ``toml`` block that ``trace.toml`` accepts, and name each of Poisson Tasks' nine labels and
  each kind they give by default; and they say ``rules`` and ``budgets`` apply to a run Prove
  swept (LK-9, LK-26, ruled 2026-11-16).
- PL-61: no other page moves, nor the CHANGELOG (``test_pl_unchanged.py``, PL-56); the
  CHANGELOG's line is the release cut's to write, as trace#31's was (F31-15).
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from pl_pins import PINS, REPO
from pl_support import TASKS_LABELS

PAGE = "docs/config.md"
PART = "### `[taxonomy]`"


def _main() -> list[str]:
    return str(json.loads(PINS.read_text(encoding="utf-8"))["texts"]["files"][PAGE]).split("\n")


def _now() -> list[str]:
    return (REPO / PAGE).read_text(encoding="utf-8").split("\n")


def _added() -> list[str]:
    old, new = _main(), _now()
    ops = [op for op in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes() if op[0] != "equal"]
    assert ops and all(tag == "insert" for tag, *_ in ops), ops
    start = next(i for i, line in enumerate(new) if line.startswith(PART))
    end = next(i for i in range(start + 1, len(new)) if new[i].startswith("## ") or new[i].startswith("### "))
    for _, _, _, j1, j2 in ops:
        assert start < j1 and j2 <= end, (j1, j2, start, end)
    return [line for _, _, _, j1, j2 in ops for line in new[j1:j2]]


def test_pl_60_the_page_gains_lines_inside_its_taxonomy_part() -> None:
    added = _added()
    assert any(line.strip() for line in added)


def test_pl_60_it_names_the_setting_and_shows_a_table_trace_accepts(tmp_path: Path) -> None:
    from poisson_trace import config

    text = "\n".join(_added())
    assert "`labels`" in text and "[taxonomy.labels]" in text
    blocks = re.findall(r"```toml\n(.*?)```", text, flags=re.S)
    assert blocks and any("[taxonomy.labels]" in b for b in blocks)
    for block in blocks:
        path = tmp_path / "trace.toml"
        path.write_text("version = 1\n\n" + block, encoding="utf-8")
        held = config.load(str(path))
        assert held.labels, block


def test_pl_60_it_names_each_tasks_label_and_its_kind() -> None:
    text = " ".join(_added())
    for label, kind in TASKS_LABELS.items():
        assert f"`{label}`" in text, label
        assert f"`{kind}`" in text, kind


def test_pl_60_it_says_the_rules_apply_to_a_run_prove_swept() -> None:
    """LK-9 (ruled 2026-11-16): a team's ``[[taxonomy.rules]]`` apply to runs Prove swept."""
    paragraphs = " ".join(line.strip() or "\n" for line in _added()).split("\n")
    assert any("`rules`" in p and "run Prove swept" in p for p in paragraphs), paragraphs


def test_pl_60_it_says_the_budgets_apply_to_a_run_prove_swept() -> None:
    """LK-26 (budgets ruled no 2026-11-16): ``[signals.budgets]`` apply to runs Prove swept, and
    the page says which of a swept try's signals each budget reads."""
    paragraphs = " ".join(line.strip() or "\n" for line in _added()).split("\n")
    said = [p for p in paragraphs if "`budgets`" in p and "run Prove swept" in p]
    assert said, paragraphs
    for budget in ("max_wall_time_s", "max_total_tokens", "max_cost_usd", "cost_usd"):
        assert any(f"`{budget}`" in p for p in said), budget
