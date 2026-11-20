"""PL-40 and PL-41: the recipe's failures by kind (``docs/recipes/with-tasks-and-prove.md``, its
files under ``examples/three-tools/``).

- PL-40 (slow): run as the page runs them (both sweeps with the page's salt, ``init`` with the
  answer the page gives, ``fix-check`` as the page asks it), the lost-token failures read as the
  kind their label ``wrong_state`` gives, ``wrong_answer``: ``fix-check``'s ``Failures by kind``
  prints ``FROZEN``, which is what main printed with that one word in place of
  ``unclassified_error``, and no note.
- PL-41 (its fast twin): Prove's wrapper, called for every committed task on a few seeds of both
  versions and stored through Prove's own store: every failed try is labelled ``wrong_state``
  and reads ``wrong_answer``, with no signal; ``fix-check`` counts them under that kind alone,
  with no note.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from label_kinds_support import EXAMPLE, config, kind_rows, run, section

SALT = "7f3a2c"
RUNS = {"before": "agent before", "after": "agent after"}
OPENING = ("Each failed try's kind of failure, by the built-in rules; the same rules classified both runs. Counts, not a test: "
           "the verdict above is about all failures together.")
#: What it prints under the rule.
FROZEN = [
    "## Failures by kind",
    "",
    OPENING,
    "",
    "| kind | old | old share | new | new share | change |",
    "|---|---|---|---|---|---|",
    "| wrong_answer | 1,320 | 25.4% | 0 | 0.0% | -25.4 points |",
    "| all failures | 1,320 | 25.4% | 0 | 0.0% | -25.4 points |",
    "",
    "of 5,200 tries of the old version and 5,200 of the new; a try has one kind",
]


@pytest.mark.slow
def test_pl_40_the_recipes_failures_by_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "three-tools"
    shutil.copytree(EXAMPLE, folder, ignore=shutil.ignore_patterns("__pycache__", "prove-runs", "trace.toml"))
    prove = Path(sys.executable).parent / "poisson-prove"
    env = {**os.environ, "NO_COLOR": "1"}
    for version in ("before", "after"):
        done = subprocess.run([str(prove), "sweep", f"prove-{version}.toml", "--name", RUNS[version], "--salt", SALT, "--yes"],
                              cwd=folder, env=env, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
        assert done.returncode == 0, done.stdout + done.stderr
    monkeypatch.chdir(folder)
    made = run(["init", "--yes", "--event", "wrong_state"])
    assert made.code == 0, made.text
    ran = run(["fix-check", RUNS["before"], RUNS["after"], "--inputs", "all", "--max-mde", "0.20"])
    assert ran.code == 0, ran.text
    assert section(ran.out) == FROZEN
    assert "Trace has no kind" not in ran.out


def test_pl_41_the_wrappers_tries_read_wrong_answer(tmp_path: Path) -> None:
    from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash

    from poisson_trace.ingest.prove import read_rows

    sys.path.insert(0, str(EXAMPLE))
    try:
        import prove_rollout
    finally:
        sys.path.remove(str(EXAMPLE))
    assert Path(prove_rollout.__file__).resolve().parent == EXAMPLE.resolve()
    root = tmp_path / "prove-runs"
    store = Store(root)
    for n, version in enumerate(("before", "after")):
        run_id = f"20261116T09000{n}Z-000{n}"
        store.create_run(RunManifest(run_id=run_id, target_id="agent", t_unit="steps", run_salt=SALT,
                                     axis_types={"task": "categorical"}, backend="local", environment={},
                                     created_at=f"2026-11-16T09:00:0{n}Z", name=RUNS[version]))
        records = []
        for task in sorted(prove_rollout.TASKS):
            config_ = {"task": task}
            for seed in range(4):
                episode = getattr(prove_rollout, version)(config_, seed)
                records.append(EpisodeRecord.from_episode(episode, run_id=run_id, config=config_, seed=seed,
                                                          replicate_index=seed, wall_time=0.01))
        store.append(run_id, records)
        store.mark_complete(run_id)
        rows = read_rows(root, run_id, failed=("wrong_state",))
        frame = store.read(run_id, meta=False, trace="none")
        failed = [r for r in rows if r.result == "fail"]
        assert {str(o) for o in frame["outcome"]} <= {"passed", "wrong_state"}
        assert len(failed) == int((frame["outcome"] == "wrong_state").sum())
        assert all(r.failure_kind == "wrong_answer" and r.signals == () for r in failed)
        assert all(r.failure_kind is None for r in rows if r.result == "pass")
        assert (len(failed) > 0) == (version == "before")
        assert {r.case for r in rows} == {config_hash({"task": t}) for t in prove_rollout.TASKS}
    path = config(tmp_path, root.name, ["wrong_state"])
    ran = run(["fix-check", RUNS["before"], RUNS["after"], "--inputs", "all", "--max-mde", "0.9", "--config", path])
    assert ran.code == 0, ran.text
    lines = section(ran.out)
    rows_ = kind_rows(lines)
    assert list(rows_) == ["wrong_answer", "all failures"]
    assert rows_["wrong_answer"] == rows_["all failures"]
    assert rows_["wrong_answer"][2] == "0"
    assert lines[2] == OPENING
    assert "Trace has no kind" not in ran.out
