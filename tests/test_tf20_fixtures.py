"""TF20-10 to TF20-35: the recipe's fixtures under ``examples/three-tools/`` (spec section 17.6;
the brief's rules 2, 3 and 4). The agent's and the wrapper's contract is written once, in
``tf20_support``'s opening.

**Rule 2: the tasks are Tasks' own, byte for byte.**

- TF20-10: ``tasks/`` holds the two files ``generate`` writes and nothing else: ten tasks at
  depth 1 and ten at depth 3, one call and three, the same ten seeds in the same order at both
  levels, so that only the number of steps differs between them.
- TF20-11: ``generate``, run now with section 17.6's command in an empty folder with a home of
  its own and every connection refused, writes those two files byte for byte and nothing else.
- TF20-12: ``PROVENANCE.md`` names the Tasks version and the command, word for word, and gives
  each file's SHA-256, which is the committed file's.
- TF20-13: the environment has Tasks at the pin and Prove at Trace's.

**Rule 3: the stand-in agent.**

- TF20-20: ``agent.py`` imports no model client, nothing that reaches the network and no part of
  Tasks that runs a model; ``prove_rollout.py`` and the pytest file neither, but for Prove and
  the task's checker.
- TF20-21: both versions run on every task with every connection refused.
- TF20-22: ``agent.py`` carries a comment where a real agent's model call would go.
- TF20-23: ``after`` makes the task's reference calls, on every task and seed.
- TF20-24: ``before`` makes them too, but on a step after the first may pass a token that is not
  the one the step before returned, and then stops; it never loses the token on the first step,
  never changes anything else, and on a one-step task is the reference.
- TF20-25: the share is seeded: the same seed gives the same calls, and over the seeds the token
  is lost at each later step on a share of them, never on none and never on all.
- TF20-26: the task's own checker passes what ``after`` does and fails what ``before`` does when
  it loses the token, and nothing else of ``before``'s.
- TF20-27: run whole, the page's ``where "agent before"`` places every failed try at the step its
  token was lost: in Prove's stored run, a try failed exactly when the agent lost the token on
  its seed, and its ``t`` is that step; ``where`` prints those steps and no other.
- TF20-28: the files a reader opens are in plain words (TF0-21's rule, over the example).

**Rule 4: the spec files and the wrapper.**

- TF20-30: the two spec files differ only in the target, ``prove_rollout:before`` and
  ``prove_rollout:after``: one line, and nothing else.
- TF20-31: every label of the task's checker is declared an outcome, every one but ``passed`` a
  failure, and ``passed`` the success.
- TF20-32: one axis, its values the twenty committed tasks, one each.
- TF20-33: the wrapper runs the task its axis names: the outcome is the checker's label of the
  agent's calls, ``t`` the number of calls, the case the axis value, and each call a ``tool``
  span of the trace, in order.
- TF20-34: the replicates are what Prove's power gate asks of the page's sweeps: run as the page
  runs them, a dry run passes at the spec's replicates and is refused one below.
- TF20-35: run whole, the page's two runs are complete and as declared: every task at the
  replicates, every outcome a checker's label, the old version failing and the new never.
- TF20-36: the episode's horizon is the number of model calls a Tasks run allows, 32
  (``poisson_tasks.taskset.MAX_MODEL_CALLS`` at the pin), not the task's own number of calls
  (Taylor's ruling on TT-16, 2026-11-15): on every task and seed of both versions, and on every
  try of the page's two stored runs, each try's ``t`` below it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tf20_support import (
    EXAMPLE, GENERATE, HORIZON, LEVELS, NETWORK, PROVE_VERSION, PROVENANCE, RUNS, SPECS, TARGETS, TASK_DIR, TASK_FILES, TASKS_PER_LEVEL, TASKS_VERSION, Ran,
    all_tasks, calls_of, every_command, imported, load, outcomes, pytest_file, rows, shared_run, store_of, tasks, toml,
)

SEEDS = range(200)


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Ran]:
    yield shared_run(tmp_path_factory)


def _verify(task: dict[str, Any], calls: list[tuple[str, dict[str, Any]]]) -> str:
    from poisson_tasks.export import ExportTaskData, bundle_from_data
    from poisson_tasks.tasks import FormatSpec, Turn, verify

    bundle = bundle_from_data(ExportTaskData.model_validate(task))
    turns = tuple(Turn("", ((name, arguments),), "tool_calls") for name, arguments in calls) + (Turn("Done.", (), "stop"),)
    return str(verify(bundle, turns, True, False, FormatSpec("direct", ())).label)


def _lost(task: dict[str, Any], calls: list[tuple[str, dict[str, Any]]]) -> int | None:
    """The step (counting from 1) at which ``calls`` passed a token that is not the reference's,
    or None."""
    for at, ((name, arguments), (ref_name, ref_arguments)) in enumerate(zip(calls, calls_of(task), strict=False), 1):
        if (name, arguments) != (ref_name, ref_arguments):
            return at
    return None


# ---------- TF20-10 ----------


def test_tf20_10_the_tasks_are_the_two_files_generate_writes() -> None:
    assert sorted(p.name for p in TASK_DIR.iterdir()) == sorted(TASK_FILES)
    seeds = []
    for name in TASK_FILES:
        arm, depth = LEVELS[name]
        found = tasks(name)
        assert len(found) == TASKS_PER_LEVEL, (name, len(found))
        assert {t["arm_id"] for t in found} == {arm}
        assert {len(t["reference_calls"]) for t in found} == {depth}, name
        seeds.append([t["seed"] for t in found])
        assert len({t["task_id"] for t in found}) == TASKS_PER_LEVEL
    assert seeds[0] == seeds[1], "the same tasks at both levels, by seed"


# ---------- TF20-11 ----------


def test_tf20_11_generate_writes_the_committed_files_byte_for_byte(tmp_path: Path) -> None:
    import shutil
    import sys

    work, home, guard = tmp_path / "work", tmp_path / "home", tmp_path / "guard"
    for folder in (work, home, guard):
        folder.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import socket\n"
        "def _refused(*args, **kwargs):\n"
        "    raise OSError('generate reached for the network')\n"
        "socket.socket.connect = _refused\n", encoding="utf-8")
    command = shutil.which("poisson-tasks", path=str(Path(sys.executable).parent))
    assert command, "poisson-tasks is installed in this environment"
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "VIRTUAL_ENV", "POISSON_TASKS_CONFIG")}
    env.update(HOME=str(home), PYTHONPATH=str(guard))
    done = subprocess.run([command, *GENERATE[1:]], cwd=work, env=env, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stdout + done.stderr
    assert sorted(p.relative_to(work).as_posix() for p in work.rglob("*") if p.is_file()) == [f"tasks/{n}" for n in sorted(TASK_FILES)]
    for name in TASK_FILES:
        assert (work / "tasks" / name).read_bytes() == (TASK_DIR / name).read_bytes(), name
    assert list(home.iterdir()) == [], "generate writes nothing to the home folder"


# ---------- TF20-12 ----------


def test_tf20_12_the_provenance_names_the_version_the_command_and_the_digests() -> None:
    text = PROVENANCE.read_text(encoding="utf-8")
    assert re.search(rf"(?:poisson-tasks|Poisson Tasks)[ =]+{re.escape(TASKS_VERSION)}\b", text), "the Tasks version"
    for version in re.findall(r"(?:poisson-tasks|Poisson Tasks)[ =]+(\d+\.\d+\.\d+(?:[a-z]+\d+)?)", text):
        assert version == TASKS_VERSION, version
    assert shlex.join(GENERATE) in text, "the command, word for word"
    for name in TASK_FILES:
        digest = hashlib.sha256((TASK_DIR / name).read_bytes()).hexdigest()
        assert re.search(rf"\b{digest}\b[^\n]*\b{re.escape(name)}\b|\b{re.escape(name)}\b[^\n]*\b{digest}\b", text), f"{name}'s SHA-256"


# ---------- TF20-13 ----------


def test_tf20_13_the_environment_has_the_pinned_versions() -> None:
    from importlib.metadata import version

    from pin_support import RECORDED, at_or_above_the_floor

    assert version("poisson-tasks") == TASKS_VERSION
    # Prove at the floor or above it, not at one exact version (ruled 2026-11-17, PV-7)
    assert PROVE_VERSION == RECORDED and at_or_above_the_floor(version("poisson-prove")), version("poisson-prove")


# ---------- TF20-20 ----------


def test_tf20_20_the_agent_calls_no_model_and_reaches_no_network() -> None:
    for name in ("agent.py", "prove_rollout.py", pytest_file().name):
        hits = sorted(imported(EXAMPLE / name) & set(NETWORK))
        assert hits == [], f"{name} imports {hits}"
    agent = imported(EXAMPLE / "agent.py")
    assert not {name for name in agent if name.split(".")[0] in ("poisson_tasks", "poisson_prove", "poisson_trace")}, \
        "the agent is the team's own code: it does not lean on the tools that test it"


# ---------- TF20-21 ----------


def test_tf20_21_both_versions_run_with_every_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = load("agent")

    def refused(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the agent reached for the network")

    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket, "create_connection", refused)
    for task in all_tasks():
        for seed in range(5):
            assert agent.before(task, seed) and agent.after(task, seed)


# ---------- TF20-22 ----------


def test_tf20_22_a_comment_where_the_model_call_would_go() -> None:
    lines = (EXAMPLE / "agent.py").read_text(encoding="utf-8").split("\n")
    comments = [line for line in lines if line.strip().startswith("#")]
    assert any(re.search(r"(?i)\bmodel\b", line) for line in comments), "a comment where a real agent's model call would go"


# ---------- TF20-23 ----------


def test_tf20_23_after_makes_the_reference_calls() -> None:
    agent = load("agent")
    for task in all_tasks():
        for seed in range(50):
            got = agent.after(task, seed)
            assert [(name, dict(arguments)) for name, arguments in got] == calls_of(task), (task["task_id"][:12], seed)


# ---------- TF20-24 ----------


def test_tf20_24_before_loses_the_token_on_a_later_step_and_stops() -> None:
    agent = load("agent")
    for task in all_tasks():
        reference = calls_of(task)
        for seed in SEEDS:
            got = [(name, dict(arguments)) for name, arguments in agent.before(task, seed)]
            lost = _lost(task, got)
            if lost is None:
                assert got == reference, (task["task_id"][:12], seed)
                continue
            assert lost > 1, "never on the first step"
            assert len(got) == lost, "it makes no call after the one that lost the token"
            name, arguments = got[-1]
            ref_name, ref_arguments = reference[lost - 1]
            assert name == ref_name and set(arguments) == set(ref_arguments), (got[-1], reference[lost - 1])
            assert {k for k in arguments if arguments[k] != ref_arguments[k]} == {"chain_token"}, (got[-1], reference[lost - 1])
            assert arguments["chain_token"] != ref_arguments["chain_token"]
        if len(reference) == 1:
            assert all(agent.before(task, seed) == agent.after(task, seed) for seed in range(20))


# ---------- TF20-25 ----------


def test_tf20_25_the_share_is_seeded() -> None:
    agent = load("agent")
    deep = [task for task in all_tasks() if len(task["reference_calls"]) > 1]
    assert deep
    reached: Counter[int] = Counter()
    lost: Counter[int] = Counter()
    for task in deep:
        for seed in SEEDS:
            first = agent.before(task, seed)
            assert agent.before(task, seed) == first, "the same seed, the same calls"
            at = _lost(task, [(n, dict(a)) for n, a in first])
            for step in range(2, (at or len(task["reference_calls"])) + 1):
                reached[step] += 1
            if at is not None:
                lost[at] += 1
    for step in range(2, max(len(t["reference_calls"]) for t in deep) + 1):
        share = lost[step] / reached[step]
        assert 0.05 < share < 0.95, (step, lost[step], reached[step])
    differs = sum(agent.before(deep[0], seed) != agent.before(deep[0], seed + 1) for seed in range(50))
    assert differs > 0, "another seed, other calls"


# ---------- TF20-26 ----------


def test_tf20_26_the_task_s_checker_fails_a_lost_token_and_nothing_else() -> None:
    agent = load("agent")
    for task in all_tasks():
        assert _verify(task, [(n, dict(a)) for n, a in agent.after(task, 0)]) == "passed"
        for seed in range(30):
            calls = [(n, dict(a)) for n, a in agent.before(task, seed)]
            label = _verify(task, calls)
            assert (label == "passed") == (_lost(task, calls) is None), (task["task_id"][:12], seed, label)
            assert label in outcomes()


# ---------- TF20-27 ----------


def test_tf20_27_where_places_every_failed_try_at_the_step_its_token_was_lost(ran: Ran) -> None:
    agent, wrapper = load("agent"), load("prove_rollout")
    table = rows(store_of(ran.root, RUNS["before"]))
    steps: Counter[int] = Counter()
    for row in table.itertuples():
        value = next(iter(json.loads(row.config).values()))
        task = wrapper.task(value)
        calls = [(n, dict(a)) for n, a in agent.before(task, int(row.seed))]
        lost = _lost(task, calls)
        assert (row.outcome != "passed") == (lost is not None), (value, row.seed, row.outcome)
        if lost is not None:
            assert int(row.t) == lost, (value, row.seed, row.t, lost)
            steps[lost] += 1
    assert steps and min(steps) >= 2
    where = [c for c in ran.checked if c.command.split("&&")[-1].strip().startswith(f'poisson-trace where "{RUNS["before"]}"')]
    assert where and where[0].code == 0
    table_lines = re.findall(r"(?m)^\| (\d+) \| [\d,]+ \| ([\d,]+) \|", where[0].printed.split("## Share not yet failed, by step")[1].split("##")[0])
    printed = {int(step) for step, failed in table_lines if failed != "0"}
    assert printed == set(steps), (printed, dict(steps))


# ---------- TF20-28 ----------


def test_tf20_28_the_example_s_files_are_in_plain_words() -> None:
    from tf0_support import plain

    read = [path for path in sorted(EXAMPLE.rglob("*")) if path.is_file() and path.suffix in (".py", ".md", ".toml") and "__pycache__" not in path.parts]
    assert {"agent.py", "prove_rollout.py", "PROVENANCE.md", "prove-before.toml", "prove-after.toml"} <= {p.name for p in read}, read
    for path in read:
        assert plain(path.read_text(encoding="utf-8")) == [], path.name


# ---------- TF20-30 ----------


def test_tf20_30_the_spec_files_differ_only_in_the_target() -> None:
    before, after = (SPECS[v].read_text(encoding="utf-8").split("\n") for v in ("before", "after"))
    assert len(before) == len(after)
    differ = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert differ == [(f'target = "{TARGETS["before"]}"', f'target = "{TARGETS["after"]}"')], differ
    parsed = {v: toml(SPECS[v]) for v in SPECS}
    assert parsed["before"]["target"] == TARGETS["before"] and parsed["after"]["target"] == TARGETS["after"]


# ---------- TF20-31 ----------


def test_tf20_31_every_label_but_passed_is_a_failure() -> None:
    declare = toml(SPECS["before"])["declare"]
    assert set(declare["outcomes"]) == set(outcomes()) and len(declare["outcomes"]) == len(outcomes())
    assert set(declare["failures"]) == set(outcomes()) - {"passed"} and len(declare["failures"]) == len(outcomes()) - 1
    assert declare.get("successes") == ["passed"]


# ---------- TF20-32 ----------


def test_tf20_32_one_axis_one_task_a_value() -> None:
    spec = toml(SPECS["before"])
    assert len(spec["axes"]) == 1 and not spec.get("scenarios")
    (axis, table), = spec["axes"].items()
    assert table["type"] == "categorical"
    values = table["values"]
    assert len(values) == len(set(values)) == 2 * TASKS_PER_LEVEL
    wrapper = load("prove_rollout")
    named = [wrapper.task(value)["task_id"] for value in values]
    assert sorted(named) == sorted(t["task_id"] for t in all_tasks()), "each committed task once"


# ---------- TF20-33 ----------


@pytest.mark.parametrize("version", ["before", "after"])
def test_tf20_33_the_wrapper_runs_the_named_task_through_its_checker(version: str) -> None:
    from poisson_prove import Episode

    agent, wrapper = load("agent"), load("prove_rollout")
    spec = toml(SPECS[version])
    (axis, table), = spec["axes"].items()
    target = getattr(wrapper, TARGETS[version].split(":")[1])
    for value in table["values"]:
        task = wrapper.task(value)
        for seed in range(12):
            episode = target({axis: value}, seed)
            assert isinstance(episode, Episode)
            calls = [(n, dict(a)) for n, a in getattr(agent, version)(task, seed)]
            assert episode.outcome == _verify(task, calls), (value, seed)
            assert episode.t == len(calls) and episode.t <= episode.horizon
            assert episode.meta["case_id"] == value
            from poisson_prove.trace import Trace

            spans = [s for s in Trace.from_dict(episode.meta["trace"]).ordered() if s.kind == "tool"]
            assert [s.name for s in spans] == [name for name, _ in calls], (value, seed)


# ---------- TF20-34 ----------


def _sweep_blocks() -> dict[str, str]:
    out: dict[str, str] = {}
    for _, block, command in every_command():
        if command[:2] == ["poisson-prove", "sweep"]:
            for version, path in SPECS.items():
                if any(Path(word).name == path.name for word in command):
                    out[version] = block.body.replace("\\\n", " ").strip()
    return out


@pytest.mark.parametrize("version", ["before", "after"])
def test_tf20_34_the_replicates_are_what_the_power_gate_asks(ran: Ran, tmp_path: Path, version: str) -> None:
    replicates = toml(SPECS[version])["replicates"]
    line = _sweep_blocks()[version]
    dry = re.sub(r'\s--name\s+("[^"]*"|\S+)', "", line)
    dry = re.sub(r"\s--yes\b", "", dry) + " --dry-run"
    home = ran.own_home(tmp_path)
    at = ran.run(f"{dry} --replicates {replicates}", home)
    below = ran.run(f"{dry} --replicates {replicates - 1}", home)
    assert at.returncode == 0, at.stdout + at.stderr
    assert below.returncode == 1 and re.search(r"(?m)^error: (underpowered design|no single condition)", below.stdout + below.stderr), \
        below.stdout + below.stderr
    assert re.search(rf"--replicates {replicates}\b", below.stdout + below.stderr), "the gate names the spec's replicates as the ones it needs"


# ---------- TF20-35 ----------


def test_tf20_35_the_two_runs_are_complete_and_as_declared(ran: Ran) -> None:
    spec = toml(SPECS["before"])
    (axis, table), = spec["axes"].items()
    for version, name in RUNS.items():
        run = store_of(ran.root, name)
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "complete" and manifest["environment"]["import_path"] == TARGETS[version]
        # the stamp is the installed Prove's, at the floor or above it (ruled 2026-11-17, PV-5)
        from pin_support import installed

        assert manifest["environment"]["poisson_prove_version"] == installed()
        assert manifest["declared"]["failures"] == sorted(spec["declare"]["failures"])
        found = rows(run)
        per = Counter(json.loads(c)[axis] for c in found["config"])
        assert per == {value: spec["replicates"] for value in table["values"]}, version
        assert set(found["outcome"]) <= set(outcomes()) and found["outcome"].notna().all()
        assert (found["case_id"] == [json.loads(c)[axis] for c in found["config"]]).all()
        if version == "after":
            assert set(found["outcome"]) == {"passed"}
        else:
            assert "passed" in set(found["outcome"]) and len(set(found["outcome"])) > 1


# ---------- TF20-36 ----------


def test_tf20_36_the_horizon_is_the_model_calls_a_tasks_run_allows(ran: Ran) -> None:
    from poisson_tasks.taskset import MAX_MODEL_CALLS

    assert MAX_MODEL_CALLS == HORIZON
    wrapper = load("prove_rollout")
    spec = toml(SPECS["before"])
    (axis, table), = spec["axes"].items()
    for version, target in TARGETS.items():
        run = getattr(wrapper, target.split(":")[1])
        for value in table["values"]:
            for seed in range(12):
                episode = run({axis: value}, seed)
                assert episode.horizon == HORIZON and episode.t < HORIZON, (version, value, seed, episode.horizon)
        found = rows(store_of(ran.root, RUNS[version]))
        assert set(found["horizon"]) == {HORIZON}, (version, set(found["horizon"]))
        assert (found["t"] < HORIZON).all(), version
