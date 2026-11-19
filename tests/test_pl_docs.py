"""PL-60: the config's page says how a team names its labels' kinds.

- PL-60: the ``[taxonomy]`` part of ``docs/config.md`` names the setting ``labels`` and the table
  ``[taxonomy.labels]``, shows it in a ``toml`` block that ``trace.toml`` accepts, and names each
  of Poisson Tasks' nine labels and each kind they give by default; and it says ``rules`` and
  ``budgets`` apply to a run Prove swept.

The part is read as it stands.
"""

from __future__ import annotations

import re
from pathlib import Path

from pl_pins import REPO
from pl_support import TASKS_LABELS

PAGE = "docs/config.md"
PART = "### `[taxonomy]`"


def _part() -> list[str]:
    """The lines of the page's ``[taxonomy]`` part, under its heading and up to the next one."""
    page = (REPO / PAGE).read_text(encoding="utf-8").split("\n")
    start = next(i for i, line in enumerate(page) if line.startswith(PART))
    end = next(i for i in range(start + 1, len(page)) if page[i].startswith(("## ", "### ")))
    return page[start + 1:end]


def test_pl_60_it_names_the_setting_and_shows_a_table_trace_accepts(tmp_path: Path) -> None:
    from poisson_trace import config

    text = "\n".join(_part())
    assert "`labels`" in text and "[taxonomy.labels]" in text
    blocks = [b for b in re.findall(r"```toml\n(.*?)```", text, flags=re.S) if "[taxonomy.labels]" in b]
    assert blocks
    for block in blocks:
        path = tmp_path / "trace.toml"
        path.write_text("version = 1\n\n" + block, encoding="utf-8")
        held = config.load(str(path))
        assert held.labels, block


def test_pl_60_it_names_each_tasks_label_and_its_kind() -> None:
    text = " ".join(_part())
    for label, kind in TASKS_LABELS.items():
        assert f"`{label}`" in text, label
        assert f"`{kind}`" in text, kind


def test_pl_60_it_says_the_rules_apply_to_a_run_prove_swept() -> None:
    """A team's ``[[taxonomy.rules]]`` apply to runs Prove swept."""
    paragraphs = " ".join(line.strip() or "\n" for line in _part()).split("\n")
    assert any("`rules`" in p and "run Prove swept" in p for p in paragraphs), paragraphs


def test_pl_60_it_says_the_budgets_apply_to_a_run_prove_swept() -> None:
    """``[signals.budgets]`` apply to runs Prove swept, and
    the page says which of a swept try's signals each budget reads."""
    paragraphs = " ".join(line.strip() or "\n" for line in _part()).split("\n")
    said = [p for p in paragraphs if "`budgets`" in p and "run Prove swept" in p]
    assert said, paragraphs
    for budget in ("max_wall_time_s", "max_total_tokens", "max_cost_usd", "cost_usd"):
        assert any(f"`{budget}`" in p for p in said), budget
