"""A small suite that replays the stored HumanEval outcomes, for the JUnit fixture's second pair.

Not collected by Trace's own suite (its name does not begin with ``test_``); ``make.py`` runs it
by name. It reads one stored run of the committed HumanEval store, named by ``REPLAY_STORE`` and
``REPLAY_RUN``, and holds one test per problem at temperature 0.7 in each of four classes, one
class per replicate (0 to 3): a test passes when that episode passed, fails on an assertion when
the episode failed its assertions, and errors in its setup when the episode crashed.
"""

import os

import pytest
from poisson_prove.store import Store

REPEATS = 4
TEMPERATURE = 0.7

_frame = Store(os.environ["REPLAY_STORE"]).read(os.environ["REPLAY_RUN"], meta=False)
OUTCOMES = {
    (row.config["task_id"], int(row.replicate_index)): row.outcome
    for row in _frame.itertuples(index=False)
    if row.config["temperature"] == TEMPERATURE and row.replicate_index < REPEATS
}
TASKS = sorted({task for task, _ in OUTCOMES}, key=lambda t: int(t.split("/")[1]))


def _episode(task: str, repeat: int) -> str:
    outcome = OUTCOMES[(task, repeat)]
    if outcome == "crashed":
        raise RuntimeError("the episode crashed before its tests ran")
    return outcome


class TestRepeat0:
    @pytest.fixture
    def outcome(self, task: str) -> str:
        return _episode(task, 0)

    @pytest.mark.parametrize("task", TASKS)
    def test_solves(self, outcome: str) -> None:
        assert outcome == "passed"


class TestRepeat1:
    @pytest.fixture
    def outcome(self, task: str) -> str:
        return _episode(task, 1)

    @pytest.mark.parametrize("task", TASKS)
    def test_solves(self, outcome: str) -> None:
        assert outcome == "passed"


class TestRepeat2:
    @pytest.fixture
    def outcome(self, task: str) -> str:
        return _episode(task, 2)

    @pytest.mark.parametrize("task", TASKS)
    def test_solves(self, outcome: str) -> None:
        assert outcome == "passed"


class TestRepeat3:
    @pytest.fixture
    def outcome(self, task: str) -> str:
        return _episode(task, 3)

    @pytest.mark.parametrize("task", TASKS)
    def test_solves(self, outcome: str) -> None:
        assert outcome == "passed"
