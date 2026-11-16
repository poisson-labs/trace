"""The team's agent, as a stand-in: it calls no model, so this example costs nothing to run.

A task asks the agent to move a record through one or more stages. Each stage is a tool call,
and each stage after the first needs the token the stage before returned (its `chain_token`).

There are two versions of the agent here, the one before a change and the one after:

- `before` has the fault the change fixes. On a share of the steps after the first it loses the
  token: it passes an empty one, the tool refuses it, and the agent stops.
- `after` carries the token every time.

Both take one task (a line of a file in `tasks/`, read as JSON) and a seed, and return the tool
calls they made, in order, as `(name, arguments)` pairs.
"""

from __future__ import annotations

import random
from typing import Any

Call = tuple[str, dict[str, Any]]

#: On a step after the first, how often the old version loses the token.
LOSES_TOKEN = 0.3


def _next_call(task: dict[str, Any], step: int) -> Call:
    # A real agent calls its model here, with the request and what the last tool returned, and
    # the model chooses the call. The stand-in reads the call from the task's reference solution.
    name, arguments = task["reference_calls"][step]
    return name, dict(arguments)


def before(task: dict[str, Any], seed: int) -> list[Call]:
    """The old version: on some later steps it loses the token, and stops there."""
    chance = random.Random(f"{task['task_id']}:{seed}")
    made: list[Call] = []
    for step in range(len(task["reference_calls"])):
        name, arguments = _next_call(task, step)
        if step > 0 and chance.random() < LOSES_TOKEN:
            made.append((name, {**arguments, "chain_token": ""}))
            break
        made.append((name, arguments))
    return made


def after(task: dict[str, Any], seed: int) -> list[Call]:
    """The new version: every call the task needs, with the token carried each time."""
    return [_next_call(task, step) for step in range(len(task["reference_calls"]))]
