"""What Prove runs: one task, one try of the agent, judged by the task's own checker.

The two spec files beside this one name `before` and `after` as their targets. Prove calls a
target once for each try, with the task's name and a seed, and stores the episode it returns.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import agent
from poisson_prove import Episode, record
from poisson_prove.trace import collect
from poisson_tasks.export import ExportTaskData, bundle_from_data
from poisson_tasks.tasks import FormatSpec, Turn, verify

#: The model calls a Poisson Tasks run allows one episode. Every episode here is given the same
#: room, though the stand-in never needs it: a task takes one call or three.
MAX_MODEL_CALLS = 32


def _committed() -> dict[str, dict[str, Any]]:
    """Every task in `tasks/`, named by its file and its place in it: `depth-d3-01` is the
    first line of `tasks/depth-d3.jsonl`."""
    found = {}
    for path in sorted((Path(__file__).resolve().parent / "tasks").glob("*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found[f"{path.stem}-{number:02d}"] = json.loads(line)
    return found


TASKS = _committed()


def task(name: str) -> dict[str, Any]:
    """The committed task a spec file's `task` value names."""
    return TASKS[name]


def label(chosen: dict[str, Any], calls: list[agent.Call]) -> str:
    """What a task's checker says of these calls: `passed`, or the way they failed."""
    bundle = bundle_from_data(ExportTaskData.model_validate(chosen))
    turns = [Turn("", ((name, arguments),), "tool_calls") for name, arguments in calls]
    turns.append(Turn("Done.", (), "stop"))
    return str(verify(bundle, tuple(turns), True, False, FormatSpec("direct", ())).label)


Version = Callable[[dict[str, Any], int], list[agent.Call]]


def _episode(version: Version, cfg: dict[str, Any], seed: int) -> Episode:
    chosen = task(cfg["task"])
    with collect() as collected:
        calls = version(chosen, seed)
        for step, (name, arguments) in enumerate(calls, 1):
            # Each tool call is one step of the episode's trace, so Trace can show the steps.
            sent = json.dumps(arguments, sort_keys=True)
            with record("tool", name, input=sent, step_name=f"step {step}"):
                pass
    return Episode(
        outcome=label(chosen, calls),
        t=len(calls),
        horizon=MAX_MODEL_CALLS,
        meta={"case_id": cfg["task"], "trace": collected.trace.to_dict()},
    )


def before(cfg: dict[str, Any], seed: int) -> Episode:
    """One try of the old version on the task `cfg["task"]` names."""
    return _episode(agent.before, cfg, seed)


def after(cfg: dict[str, Any], seed: int) -> Episode:
    """One try of the new version on the task `cfg["task"]` names."""
    return _episode(agent.after, cfg, seed)
