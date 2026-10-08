"""Shared helpers for the tests of names and runs (TF1-1 to TF1-17): stores whose runs carry a
chosen target, start time, status and backend, a copy of a committed fixture store to write a
names file into, the names file read back, the ``next:`` line read as a shell reads it, and a
snapshot of every file under a store.

Not a test module and not collected. Every store is written through Prove's own ``Store``; a
names file is written by ``poisson-trace name`` except where a test needs one the verb would
never write (a damaged one, a stale entry), which the test writes by hand and says so.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proofload.store import EpisodeRecord, RunManifest, Store, config_hash
from proofload.trace import Trace

from conftest import TAU2, roots
from tf0_support import RUN_ID, VERDICT_LINE, Ran, trace, trace_import

NAMES_FILE = "trace-names.toml"
# the three tau2 runs, oldest first, with the names their manifests give them (target
# tau2-airline/gpt-4.1-mini-2025-04-14@v0; started 2026-09-15 21:01Z, 21:11Z, 2026-09-17 14:02Z)
T_A, T_B, T_PILOT = "20260915T210140Z-4847", "20260915T211148Z-965d", "20260917T140219Z-2b2d"
T_NAMES = {T_A: "tau2-airline 2026-09-15 a", T_B: "tau2-airline 2026-09-15 b", T_PILOT: "tau2-airline 2026-09-17 a"}
VERBS_THAT_READ_NAMES = ("where", "compare", "fix-check", "changes", "runs", "name")
NEXT = "next: "


def tau2_copy(tmp: Path, name: str = "proofload-runs") -> Path:
    """A copy of the committed tau2 store, to write a names file into."""
    root = tmp / name
    shutil.copytree(TAU2, root)
    return root


# ---------- stores with chosen manifests ----------


@dataclass(frozen=True)
class R:
    """One run of a made store. ``rows`` outcomes in order, one input each (``case`` 0, 1, ...);
    ``traced`` gives every row a one-span trace."""

    run_id: str
    created_at: str
    target_id: str = "agent-x/model-1@v0"
    status: str = "complete"
    backend: str = "local"
    rows: tuple[str, ...] = ("fail", "ok", "fail", "ok")
    traced: bool = True


def make_runs(root: Path, runs: Sequence[R]) -> Path:
    store = Store(root)
    for r in runs:
        store.create_run(RunManifest(
            run_id=r.run_id, target_id=r.target_id, t_unit="steps", run_salt="salt", axis_types={},
            backend=r.backend, environment={}, created_at=r.created_at,
        ))
        records = []
        for i, outcome in enumerate(r.rows):
            config = {"case": str(i)}
            meta: dict[str, Any] = {}
            if r.traced:
                meta["trace"] = Trace(spans=tuple(roots(["llm"] * (2 + i % 3))), source="record").to_dict()
            records.append(EpisodeRecord(
                run_id=r.run_id, config_hash=config_hash(config), config=config, seed=i,
                replicate_index=0, outcome=outcome, t=1.0, horizon=10.0, confidence=None,
                meta=meta, error=None, wall_time=1.0, backend_meta={},
            ))
        store.append(r.run_id, records)
        if r.status == "complete":
            store.mark_complete(r.run_id)
    return root


def stamp(day: int, hour: int, minute: int = 0, second: int = 0) -> str:
    """A start time in October 2026, UTC, as Prove writes one."""
    return f"2026-10-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}.000000Z"


def run_id(day: int, hour: int, minute: int, suffix: str) -> str:
    """A run id in Prove's form, for a run started at that minute."""
    return f"202610{day:02d}T{hour:02d}{minute:02d}00Z-{suffix}"


# ---------- running and reading ----------


def where_json(store: Path | str, run: str, *extra: str) -> Ran:
    return trace(["where", run, "--store", str(store), "--event", "fail", "--json", *extra])


def resolved(store: Path | str, word: str, event: str = "fail") -> str | None:
    """The run id ``word`` names in the store, read from ``where``'s JSON; None when refused."""
    result = trace(["where", word, "--store", str(store), "--event", event, "--json"])
    if result.code != 0:
        assert result.code == 1 and result.out == "", result.text
        return None
    return str(result.json()["run"]["run_id"])


def write_names(store: Path, names: dict[str, str]) -> None:
    """A names file in the spec's form, written by hand: for a test whose subject is not
    ``name`` itself."""
    lines = ["# Poisson Trace: your names for the runs in this store. Written by `poisson-trace name`.", "version = 1", "", "[names]"]
    lines += [f"{json.dumps(n, ensure_ascii=False)} = {json.dumps(r)}" for n, r in sorted(names.items())]
    (store / NAMES_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def names_file(store: Path) -> dict[str, Any]:
    return tomllib.loads((store / NAMES_FILE).read_text(encoding="utf-8"))


def name(store: Path | str, *argv: str) -> Ran:
    return trace(["name", *argv, "--store", str(store)])


def runs_json(store: Path | str, *extra: str) -> dict[str, Any]:
    result = trace(["runs", "--store", str(store), "--json", *extra])
    assert result.code == 0, result.text
    doc: dict[str, Any] = result.json()
    return doc


def refused(result: Ran) -> str:
    """Exit 1, nothing on stdout, an ``error:`` line first; the error line."""
    assert result.code == 1, result.text
    assert result.out == "", result.out
    lines = result.lines()
    assert lines and lines[0].startswith("error: "), result.err
    return lines[0]


def first_line(result: Ran) -> str:
    return result.out.splitlines()[0] if result.out else ""


def verdict_parts(line: str) -> tuple[str, str]:
    """``(word, sentence)`` of a verdict line."""
    assert VERDICT_LINE.match(line), line
    word, _, sentence = line.partition("  ")
    return word, sentence


def next_line(result: Ran) -> str:
    """The command of the ``next:`` line that closes stdout."""
    lines = result.lines("out")
    assert lines and lines[-1].startswith(NEXT), result.out
    return lines[-1][len(NEXT):]


def shell_words(command: str) -> list[str]:
    """The words a POSIX shell makes of the command: quotes and escapes undone, a ``#`` that
    opens a word a comment, and a ``$`` or a backquote left unescaped expanded (``HOME`` is set
    to a word no name holds, so an expansion shows). Run in an empty folder."""
    with tempfile.TemporaryDirectory() as empty:
        proc = subprocess.run(
            ["/bin/sh", "-c", f"set -- {command}\nprintf '%s\\0' \"$@\""],
            capture_output=True, cwd=empty, timeout=30,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/no-home-zq7"},
        )
    assert proc.returncode == 0, (command, proc.stderr)
    return proc.stdout.decode("utf-8").split("\0")[:-1]


def positionals(command: str, verb: str) -> list[str]:
    """The words after ``poisson-trace VERB`` up to the first option."""
    words = shell_words(command)
    assert words[:2] == ["poisson-trace", verb], command
    out = []
    for word in words[2:]:
        if word.startswith("-"):
            break
        out.append(word)
    return out


def ids_in(text: str) -> list[str]:
    return RUN_ID.findall(text)


def snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    out = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        stat = path.stat()
        out[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    return out


def json_doc(result: Ran) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(result.out)
    return doc


def counts_in(sentence: str) -> list[str]:
    """The whole numbers a sentence states, separators kept."""
    return re.findall(r"(?<![\w.])\d{1,3}(?:,\d{3})*(?![\w.])", sentence)


def import_he(store: Path | str, run: str, which: str = "a") -> Ran:
    from tf0_support import deepeval_import

    return trace_import(deepeval_import(store, run, which))
