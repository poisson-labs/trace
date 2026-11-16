"""The team's own tests of its agent: every task, ten times, judged by the task's own checker.

Run it once for each version, and keep each report:

    AGENT=before pytest test_agent.py --junitxml before.xml
    AGENT=after pytest test_agent.py --junitxml after.xml
"""

from __future__ import annotations

import os

import agent
import pytest
from prove_rollout import TASKS, label

VERSION = getattr(agent, os.environ.get("AGENT", "after"))


class EveryTask:
    """One pass over the twenty tasks. Each class below is one more pass, with its own seed, so
    a report holds ten tries of each test name."""

    seed = 0

    @pytest.mark.parametrize("name", sorted(TASKS))
    def test_task(self, name: str) -> None:
        assert label(TASKS[name], VERSION(TASKS[name], self.seed)) == "passed"


for _seed in range(10):
    globals()[f"TestTry{_seed}"] = type(f"TestTry{_seed}", (EveryTask,), {"seed": _seed})
