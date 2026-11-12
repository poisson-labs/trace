"""Shared helpers for the tests of setup, the config file and doctor (TF2-1 to TF2-27): a scratch
home folder for every test, the two commands run in a fresh interpreter with stdin closed or on
a terminal that answers ``init``'s questions, the config file written and read back, stores and
result files built to order, and readers for what ``init`` and ``doctor`` print.

Not a test module and not collected. No test here searches, reads or writes the real home
folder: every test that runs ``init`` or ``doctor`` sets ``HOME`` to a folder of its own, and
runs them in a folder of its own that is not inside that home.
"""

from __future__ import annotations

import fcntl
import gzip
import json
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.store import EpisodeRecord, RunManifest, Store, config_hash

from tf0_support import DEEPEVAL, RAGAS, ESCAPED, Ran, chdir, script, trace, trace_import
from tf1_support import R, make_runs, shell_words, snapshot, stamp, tau2_copy

CONFIG = "trace.toml"
# spec section 4.5: the words that mean success, which the failure question's default leaves out
SUCCESS_WORDS = (
    "solved", "resolved", "passed", "met", "ok", "success", "fixed", "planned", "cited", "survived",
    "correct", "fresh", "fast",
)
# spec section 3.2: the keys of version 1, by table
KEYS = {
    "": ("version", "store", "events", "check", "names", "upload"),
    "store": ("path",),
    "events": ("failed",),
    "check": ("max_mde", "max_mde_hr", "fail_on"),
    "names": ("from",),
    "upload": ("enabled", "url", "token_env"),
}
# the readers a module of the install carries today, and those named in the import's tuple that are not
PRESENT_READERS = ("deepeval", "ragas")
ABSENT_READERS = ("otel", "lemma")
DOCTOR_CHECKS = ("python", "package", "prove", "config", "names", "readers")


# ---------- a home of the test's own ----------


@pytest.fixture(autouse=True)
def scratch_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``HOME`` is a folder of the test's own, beside the folders it works in, never above them."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    return home


def work(tmp_path: Path, name: str = "work") -> Path:
    """A folder to run in, beside the scratch home."""
    folder = tmp_path / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ---------- running in a fresh interpreter ----------


def run(
    argv: Sequence[Any],
    *,
    cwd: Path,
    command: str = "trace",
    prove: str = "present",
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> Ran:
    """The command in a fresh interpreter with stdin closed (never a terminal), ``HOME`` as the
    calling test set it."""
    full = dict(os.environ)
    full.update(env or {})
    proc = subprocess.run(
        [sys.executable, "-c", script(command, prove=prove), *[str(a) for a in argv]],
        stdin=subprocess.DEVNULL, capture_output=True, cwd=cwd, env=full, timeout=timeout,
    )
    return Ran(proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace"))


def _drain(fd: int, into: bytearray) -> None:
    while True:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            return
        if not chunk:
            return
        into.extend(chunk)


def _waiting(proc: subprocess.Popen[bytes], slave: int, err: bytearray, quiet: float, timeout: float) -> bool:
    """Whether the command came to wait on the terminal before it ended or ``timeout`` passed: it
    has printed on stderr, read every line typed so far, and sat asleep for ``quiet`` seconds with
    no CPU time spent and nothing more printed. A build is free to take as long as it takes
    between questions; a fixed delay would interrupt it while it still works."""
    started = time.monotonic()
    still: tuple[object, ...] | None = None
    since = started
    while time.monotonic() - started < timeout:
        if proc.poll() is not None:
            return False
        shown = subprocess.run(["ps", "-o", "stat=,time=", "-p", str(proc.pid)], capture_output=True, text=True).stdout.split()
        queued = struct.unpack("i", fcntl.ioctl(slave, termios.FIONREAD, b"\0\0\0\0"))[0]
        now = (tuple(shown), len(err))
        asleep = bool(shown) and shown[0].startswith("S") and queued == 0 and len(err) > 0
        if not asleep or now != still:
            still, since = now, time.monotonic()
        elif time.monotonic() - since >= quiet:
            return True
        time.sleep(0.05)
    return False


def _default_sigint() -> None:
    """In the child, before it starts: SIGINT at its default. A command a non-interactive shell
    starts in the background has SIGINT ignored, the child inherits that, and Python leaves an
    ignored SIGINT ignored, so the Ctrl-C a test sends would change nothing and the test would
    wait out its timeout."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def tty(
    argv: Sequence[Any],
    answers: Sequence[str],
    *,
    cwd: Path,
    interrupt: bool = False,
    prove: str = "present",
    timeout: float = 120.0,
) -> Ran:
    """``poisson-trace`` with stdin a terminal; stdout and stderr are read apart. Each answer is
    typed, one line, once the command waits on the terminal for it, as a user answers a question
    on the screen. ``interrupt`` then sends Ctrl-C (SIGINT) once the command waits for one more
    answer."""
    master, slave = os.openpty()
    attrs = termios.tcgetattr(slave)
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    proc = subprocess.Popen(
        [sys.executable, "-c", script("trace", prove=prove), *[str(a) for a in argv]],
        stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=dict(os.environ),
        preexec_fn=_default_sigint,
    )
    out, err = bytearray(), bytearray()
    assert proc.stdout is not None and proc.stderr is not None
    readers = [
        threading.Thread(target=_drain, args=(proc.stdout.fileno(), out), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr.fileno(), err), daemon=True),
    ]
    for reader in readers:
        reader.start()
    started = time.monotonic()
    try:
        for answer in answers:
            if not _waiting(proc, slave, err, 0.3, timeout):
                break
            os.write(master, (answer + "\n").encode("utf-8"))
        if interrupt and _waiting(proc, slave, err, 0.6, timeout):
            proc.send_signal(signal.SIGINT)
        try:
            code = proc.wait(timeout=max(1.0, timeout - (time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            code = ESCAPED
    finally:
        for reader in readers:
            reader.join(timeout=10)
        os.close(master)
        os.close(slave)
    return Ran(code, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"))


def here(folder: Path, argv: Sequence[Any]) -> Ran:
    """``poisson-trace`` in-process, run in ``folder``."""
    with chdir(folder):
        return trace(list(argv))


def init_yes(folder: Path, *argv: Any) -> Ran:
    """``poisson-trace init --yes`` in-process, run in ``folder``: it asks nothing."""
    return here(folder, ["init", "--yes", *argv])


def import_here(folder: Path, argv: Sequence[Any]) -> Ran:
    with chdir(folder):
        return trace_import(list(argv))


# ---------- the config file ----------


def write_config(folder: Path, text: str, name: str = CONFIG) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def config(folder: Path, name: str = CONFIG) -> dict[str, Any]:
    """The config file as TOML reads it."""
    doc: dict[str, Any] = tomllib.loads((folder / name).read_text(encoding="utf-8"))
    return doc


def config_of(store: str, events: Sequence[str] = ("unsolved",), extra: str = "") -> str:
    """A version 1 config naming one store and its failures, in the spec's form."""
    failed = ", ".join(json.dumps(e) for e in events)
    return f'version = 1\n\n[store]\npath = {json.dumps(store)}\n\n[events]\nfailed = [{failed}]\n{extra}'


# ---------- stores and result files ----------


def store_of(root: Path, runs: Sequence[R]) -> Path:
    """A store of made runs (``tf1_support.R``), written through Prove."""
    return make_runs(root, runs)


def outcome_runs(root: Path, outcomes: Sequence[Sequence[str | None]], *, target_id: str = "agent-x/model-1@v0") -> list[str]:
    """One complete run per entry, oldest first, one minute apart on 3 October 2026, each holding
    one row per outcome given; ``None`` is a row with no outcome (a timed-out row). The run ids,
    oldest first."""
    store = Store(root)
    ids = []
    for n, rows in enumerate(outcomes):
        run_id = f"20261003T{9 + n // 60:02d}{n % 60:02d}00Z-{n:04x}"
        store.create_run(RunManifest(
            run_id=run_id, target_id=target_id, t_unit="steps", run_salt="salt", axis_types={},
            backend="local", environment={}, created_at=stamp(3, 9 + n // 60, n % 60),
        ))
        records = []
        for i, outcome in enumerate(rows):
            cell = {"case": str(i)}
            if outcome is None:
                records.append(EpisodeRecord.errored(
                    run_id=run_id, config=cell, seed=i, replicate_index=0, error="timeout", wall_time=1.0, meta={},
                ))
            else:
                records.append(EpisodeRecord(
                    run_id=run_id, config_hash=config_hash(cell), config=cell, seed=i, replicate_index=0,
                    outcome=outcome, t=1.0, horizon=10.0, confidence=None, meta={}, error=None, wall_time=1.0,
                    backend_meta={},
                ))
        store.append(run_id, records)
        store.mark_complete(run_id)
        ids.append(run_id)
    return ids


def two_stores(folder: Path) -> tuple[Path, Path]:
    """``proofload-runs`` (a copy of the tau2 fixture: 3 runs, target tau2-airline) at the top,
    and ``demo/store`` (2 runs of agent-x) one folder down."""
    first = tau2_copy(folder, "proofload-runs")
    second = store_of(folder / "demo" / "store", [R("x-one", stamp(2, 9)), R("x-two", stamp(2, 10))])
    return first, second


def deepeval_file(path: Path, cases: int = 24) -> Path:
    """A DeepEval test run as DeepEval 4.2.6 wrote it: the committed fixture cut to ``cases`` test
    cases from its 91st, among which four failed, saved as plain JSON."""
    doc = json.loads(gzip.decompress((DEEPEVAL / "humaneval-a.json.gz").read_bytes()))
    doc["testCases"] = doc["testCases"][90 : 90 + cases]
    doc["conversationalTestCases"] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def ragas_rows() -> list[dict[str, Any]]:
    return [json.loads(line) for line in (RAGAS / "rag-base.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def ragas_file(path: Path) -> Path:
    """The committed Ragas table, as JSON Lines or CSV by the name's extension."""
    rows = ragas_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        columns = list(rows[0])
        lines = [",".join(columns)] + [",".join(str(row[c]) for c in columns) for row in rows]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif path.suffix == ".json":
        path.write_text(json.dumps(rows), encoding="utf-8")
    else:
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


# ---------- reading what init prints ----------

# a numbered entry of a listing: "  2) demo/store   2 runs · agent-x · newest 2026-10-02"
NUMBERED = re.compile(r"^\s*(\d+)\)\s+(\S.*?)\s*$")
# an outcome of the failure question: "1) unsolved   1,199 episodes", two to a line or one
CHOICE = re.compile(r"(\d+)\)\s+(\S+)\s+([\d,]+)\s+episodes?\b")
# a question's default, in brackets at the end of the question
DEFAULT = re.compile(r"\[([^\]\n]*)\]")


def numbered(err: str) -> dict[int, str]:
    """The listing's numbered lines, by number (the first time each number is listed)."""
    found: dict[int, str] = {}
    for line in err.splitlines():
        m = NUMBERED.match(line)
        if m and not CHOICE.search(line):
            found.setdefault(int(m.group(1)), m.group(2))
    return found


def number_of(err: str, path: str) -> int:
    """The number the listing gives the store or results at ``path``."""
    hits = [n for n, line in numbered(err).items() if line.split()[0].rstrip("/") == path]
    assert len(hits) == 1, (path, numbered(err))
    return hits[0]


def choices(err: str) -> dict[int, tuple[str, int]]:
    """The failure question's outcomes, by number: ``(outcome, episodes)``."""
    return {int(n): (word, int(c.replace(",", ""))) for n, word, c in CHOICE.findall(err)}


def last_default(err: str) -> str:
    found = DEFAULT.findall(err)
    assert found, err
    return found[-1].strip()


def numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\d+", text)}


def summary_command(out: str) -> list[str]:
    """The setup as one command, as the text summary shows it: the line that begins
    ``poisson-trace init`` and holds ``--yes``, its continuations joined, read as a shell reads it."""
    joined = re.sub(r"\\\n\s*", " ", out)
    found = [line.strip() for line in joined.splitlines() if line.strip().startswith("poisson-trace init ") and "--yes" in line]
    assert len(found) == 1, out
    return shell_words(found[0])


def refused(result: Ran) -> str:
    """Exit 1, nothing on stdout, one ``error:`` line with only ``  next:`` lines under it; the
    error line. ``init``'s progress lines may come before it on stderr."""
    assert result.code == 1 and result.out == "", result.text
    lines = result.lines()
    errors = [i for i, line in enumerate(lines) if line.startswith("error: ")]
    assert len(errors) == 1 and all(line.startswith("  next: ") for line in lines[errors[0] + 1 :]), result.err
    return lines[errors[0]]


def doc(result: Ran) -> dict[str, Any]:
    data: dict[str, Any] = result.json()
    return data


def counts(text: str) -> list[int]:
    return [int(n.replace(",", "")) for n in re.findall(r"(?<![\w.])\d{1,3}(?:,\d{3})*(?![\w.])", text)]


# ---------- doctor ----------


def doctor(folder: Path, *argv: Any) -> Ran:
    return here(folder, ["doctor", *argv])


def doctor_doc(folder: Path, *argv: Any) -> tuple[int, dict[str, Any]]:
    result = doctor(folder, *argv, "--json")
    assert result.code in (0, 4), result.text
    return result.code, doc(result)


def check(data: dict[str, Any], name: str) -> dict[str, Any]:
    found = [c for c in data["checks"] if c["name"] == name]
    assert len(found) == 1, data["checks"]
    return found[0]


# ---------- what a test watches ----------


def tree(root: Path) -> dict[str, tuple[int, int, str]]:
    """Every file under ``root``: size, modification time and digest."""
    return snapshot(root)


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every attempt to reach a host, recorded and refused."""
    tried: list[str] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        tried.append(repr(args[:2]))
        raise OSError("no network in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    yield tried


def copy_tree(source: Path, target: Path) -> Path:
    shutil.copytree(source, target, symlinks=True)
    return target
