"""Shared helpers for the tests of the Prove floor (PF-1 to PF-96): Trace declares the oldest
Prove it reads and no upper cap, and refuses a store it cannot read or write safely. Not a test
module and not collected.

The rule these tests hold (the floor takes the place of an exact pin, ``poisson-prove==0.1.3``):

1. **The floor.** ``pyproject.toml`` declares ``poisson-prove>=0.4.0`` with no upper cap.
   ``pin_support`` holds it for every test (``RECORDED``, ``REQUIREMENT``, ``INSTALL``).
2. **What Trace refuses**. The floor is read back from the installed package's own
   metadata (``look.PROVE_VERSION``). Trace reads any Prove at or above it and refuses three
   things, each in one ``error:`` line with the one command that fixes it under it:

   - a Prove below the floor: ``… through Prove (the poisson-prove package, version 0.4.0 or
     later) and found poisson-prove 0.3.0``;
   - no Prove: ``… (the poisson-prove package, version 0.4.0 or later), which is not installed
     here``;
   - a Prove that states no version: ``… and found a poisson-prove that states no version``.

   The command is ``pip install "poisson-prove>=0.4.0"``, quoted because a shell reads ``>``.
   ``doctor`` names the floor too: ``poisson-prove X (Trace reads version 0.4.0 or later)`` when
   ready, and ``poisson-prove X is installed, and Trace reads version 0.4.0 or later`` when not.
   A pre-release of the floor itself (``0.4.0rc1``) is below it, as pip orders versions, and a
   version Trace cannot read as numbers is refused as found.
3. **What does not move**. Trace goes on printing the Prove it finds
   (``--version``, ``doctor``, ``"prove": {"version"}`` in ``--json``, ``versions.prove`` in a
   saved result), and copying that Prove's ``style.css`` and ``ui.js`` into its pages. The tests
   that hold what main prints write that version as their pins hold it
   (``pin_support.as_pinned``), and check each copied file against the installed Prove's. The
   store Prove 0.1.3 made is kept as the fixture of the stored format's 1.0; the floor's own
   store, ``prove-0.4.0``, is the fixture of 1.2, and Trace reads both alike.
4. **A store in a newer format**. "Newer than Trace knows" is the store format's
   own rule (Prove 0.4.0's ``docs/artifact-format.md``): the store descriptor,
   ``.poisson/store.json``, says ``"format": "poisson.store/N"``, and a reader refuses a major
   ``N`` above the one it knows, which is 1. The minor versions (1.0, 1.1, 1.2) are written
   nowhere and only add keys a reader ignores, so they are never refused. Every command that
   reads the store or writes into it refuses such a store before anything is written, in one
   ``error:`` line that names the format found and ``poisson.store/1``, as ``import`` already
   does: ``runs``, ``name``, ``where``, ``compare``, ``fix-check``, ``changes`` (each with
   ``--json``, ``--save`` or ``--out`` where it has them), ``ui`` and ``init``, exit 1;
   ``doctor``, whose config names the store, exit 4; ``api.open_store``; and the terminal app,
   which shows the refusal on its screen and lists none of the store's runs.
5. **A store whose descriptor is broken**. ``--save`` on a store whose
   ``store.json`` is not JSON, or is JSON and not an object, refuses in one line that names the
   file, exit 1, as ``import`` does, and writes nothing. No output says ``the verdict was not
   saved: OSError``; where a verdict is printed and not saved, the note gives the system's own
   words for why (``Permission denied``).
6. **A run whose manifest cannot be read**. A word that reaches no run, in a store with a
   run Prove could not read, is refused naming that run by its id and saying Prove could not
   read it; it is no longer called an unknown run. By its id the run is refused as one Prove
   could not read, as before.
7. **CI and the release**. ``ci.yml`` has a lane that installs the newest Prove
   over the floor and runs the pull-request lane; the lanes' constraints hold the floor; the
   release check holds the floor's shape; the wheel installs beside the floor and not beside a
   Prove below it (lane J).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pin_support import FORMAT_1_0, INSTALL, OR_LATER, RECORDED

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
FIXTURES = TESTS / "fixtures"
STORES = FIXTURES / "prove-stores"
#: The stored format's 1.0, as Prove 0.1.3 wrote it, and its 1.2, as the floor writes it.
STORE_1_0 = STORES / f"prove-{FORMAT_1_0}"
STORE_1_2 = STORES / f"prove-{RECORDED}"
#: Each store's two runs, the older first, by id; each is named "agent before" and "agent after".
RUNS = {
    STORE_1_0: ("20261104T162926Z-b4d5", "20261104T162928Z-1596"),
    STORE_1_2: ("20261118T165736Z-838d", "20261118T165742Z-a070"),
}
NAMES = ("agent before", "agent after")
NOTES = ("the agent as it was", "retry each tool call once")
EVENT = ["--event", "violated"]
JUNIT = FIXTURES / "ingest" / "junit" / "trace-suite-1.xml"

STORE_FORMAT = "poisson.store/1"
NEWER = ("poisson.store/2", "poisson.store/10")

# ---------- the refusals of the floor, word for word ----------

MODULES = {"trace": "poisson_trace.cli", "import": "poisson_trace.ingest.cli"}
#: What each command does through Prove, as its refusal opens.
READS = "Poisson Trace reads stored runs"
INIT_READS = "poisson-trace init reads stores"
IMPORT_WRITES = "poisson-trace import writes runs"


def below(does: str, found: str) -> list[str]:
    return [f"error: {does} through Prove (the poisson-prove package, version {OR_LATER}) and found poisson-prove {found}", f"  next: {INSTALL}"]


def absent(does: str) -> list[str]:
    return [f"error: {does} through Prove (the poisson-prove package, version {OR_LATER}), which is not installed here", f"  next: {INSTALL}"]


def unversioned(does: str) -> list[str]:
    return [f"error: {does} through Prove (the poisson-prove package, version {OR_LATER}) and found a poisson-prove that states no version",
            f"  next: {INSTALL}"]


# ---------- running a command in a fresh interpreter ----------


class Ran:
    def __init__(self, proc: subprocess.CompletedProcess[str]) -> None:
        self.code, self.out, self.err = proc.returncode, proc.stdout, proc.stderr

    @property
    def text(self) -> str:
        return self.out + self.err

    def lines(self) -> list[str]:
        return [line for line in self.err.splitlines() if line.strip()]

    def json(self) -> Any:
        return json.loads(self.out)


def home_of(cwd: Path) -> Path:
    """The home folder of a command run in ``cwd``: a folder of its own beside it, never inside
    it or above it, since ``init`` searches neither the home folder nor a folder above it."""
    return cwd.parent / f"{cwd.name}.home"


def env_of(cwd: Path) -> dict[str, str]:
    """The environment a command runs in: a home of its own, no colour, and ``CI`` unset, since
    Trace reads it as a reason to print plain text."""
    home = home_of(cwd)
    home.mkdir(exist_ok=True)
    env = {**os.environ, "HOME": str(home), "NO_COLOR": "1"}
    for name in ("CI", "BROWSER", "POISSON_TRACE_STORE", "POISSON_TRACE_CONFIG"):
        env.pop(name, None)
    return env


def python(code: str, argv: Sequence[Any], cwd: Path, timeout: int = 300) -> Ran:
    return Ran(subprocess.run([sys.executable, "-c", code, *[str(a) for a in argv]], capture_output=True, text=True, cwd=cwd,
                              env=env_of(cwd), timeout=timeout))


def run(argv: Sequence[Any], cwd: Path, command: str = "trace") -> Ran:
    """The command, with the Prove that is installed."""
    return python(f"import sys\nfrom {MODULES[command]} import main\nsys.exit(main(sys.argv[1:]))\n", argv, cwd)


def with_fake_prove(argv: Sequence[Any], cwd: Path, prove: str, command: str = "trace") -> Ran:
    """The command in an interpreter whose ``poisson_prove`` is a stand-in: ``absent`` (the
    import fails), ``unversioned`` (a module that states no version), ``unversioned:`` and a
    Python literal (a module whose ``__version__`` is that value), or a version (a module
    stating it). A stand-in holds none of Prove's own modules, so a command that goes past the
    check with it fails, and never reads a store."""
    if prove == "absent":
        head = "sys.modules['poisson_prove'] = None\n"
    elif prove == "unversioned":
        head = "sys.modules['poisson_prove'] = types.ModuleType('poisson_prove')\n"
    elif prove.startswith("unversioned:"):
        head = f"fake = types.ModuleType('poisson_prove')\nfake.__version__ = {prove.split(':', 1)[1]}\nsys.modules['poisson_prove'] = fake\n"
    else:
        head = f"fake = types.ModuleType('poisson_prove')\nfake.__version__ = {prove!r}\nsys.modules['poisson_prove'] = fake\n"
    return python(f"import sys, types\n{head}from {MODULES[command]} import main\nsys.exit(main(sys.argv[1:]))\n", argv, cwd)


def stating(argv: Sequence[Any], cwd: Path, version: str, command: str = "trace") -> Ran:
    """The command with the Prove that is installed, whole, stating ``version``: what Trace sees
    of a Prove at that version which still holds everything Trace reads through it."""
    code = (f"import sys\nimport poisson_prove\npoisson_prove.__version__ = {version!r}\n"
            f"from {MODULES[command]} import main\nsys.exit(main(sys.argv[1:]))\n")
    return python(code, argv, cwd)


def declaring(argv: Sequence[Any], cwd: Path, requires: Sequence[str]) -> Ran:
    """The command with the installed poisson-trace declaring ``requires``, as the metadata pip
    wrote for it would say: the declaration is read through ``importlib.metadata.requires``."""
    code = ("import sys\nimport importlib.metadata as metadata\n"
            f"_requires, declared = metadata.requires, {list(requires)!r}\n"
            "metadata.requires = lambda name: list(declared) if name.replace('_', '-').lower() == 'poisson-trace' else _requires(name)\n"
            "from poisson_trace.cli import main\nsys.exit(main(sys.argv[1:]))\n")
    return python(code, argv, cwd)


# ---------- stores ----------


def tree(root: Path) -> dict[str, str]:
    """Every file under ``root`` and its digest, the scratch home left out."""
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "home" not in p.relative_to(root).parts}


def copy(store: Path, cwd: Path, name: str = "store") -> Path:
    cwd.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copytree(store, cwd / name))


def descriptor_file(root: Path) -> Path:
    return root / ".poisson" / "store.json"


def marked(store: Path, cwd: Path, found: str, name: str = "store") -> Path:
    """A copy of ``store`` whose descriptor says it is in the format ``found``, every other key
    and every other file as Prove wrote it."""
    root = copy(store, cwd, name)
    doc = json.loads(descriptor_file(root).read_text(encoding="utf-8"))
    doc["format"] = found
    descriptor_file(root).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return root


def with_descriptor(store: Path, cwd: Path, text: str, name: str = "store") -> Path:
    """A copy of ``store`` whose descriptor file holds ``text``."""
    root = copy(store, cwd, name)
    descriptor_file(root).write_text(text, encoding="utf-8")
    return root


def cut_manifest(store: Path, cwd: Path, run: str, name: str = "store") -> Path:
    """A copy of ``store`` with the manifest of ``run`` cut short, so it is no longer JSON."""
    root = copy(store, cwd, name)
    manifest = root / run / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8")[:60], encoding="utf-8")
    return root


def refused_one_line(ran: Ran, *named: str, code: int = 1) -> str:
    """The refusal's sentence: exit ``code``, nothing on stdout, one ``error:`` line that holds
    every word of ``named``, only ``next:`` lines under it, and no traceback or crash."""
    assert ran.code == code, ran.text
    assert ran.out == "", ran.out
    lines = ran.lines()
    assert lines and lines[0].startswith("error: "), ran.err
    assert all(line.startswith("  next: ") for line in lines[1:]), ran.err
    for word in named:
        assert word in lines[0], (word, lines[0])
    assert "unexpected failure" not in ran.err and "Traceback" not in ran.err, ran.err
    return lines[0]


#: Every way to read a store and every way to write into one, as the words after ``--store
#: STORE`` are given. ``A`` and ``B`` stand for the store's two runs, the older first.
READING = {
    "runs": ["runs"],
    "runs --json": ["runs", "--json"],
    "runs --all": ["runs", "--all", *EVENT],
    "name --list": ["name", "--list"],
    "where": ["where", "B", *EVENT],
    "where --json": ["where", "B", *EVENT, "--json"],
    "compare": ["compare", "A", "B", *EVENT, "--max-mde-hr", "2"],
    "compare --json": ["compare", "A", "B", *EVENT, "--max-mde-hr", "2", "--json"],
    "fix-check": ["fix-check", "A", "B", *EVENT, "--inputs", "all", "--max-mde", "0.5"],
    "fix-check --json": ["fix-check", "A", "B", *EVENT, "--inputs", "all", "--max-mde", "0.5", "--json"],
    "changes": ["changes", "A", "B", *EVENT],
    "changes --json": ["changes", "A", "B", *EVENT, "--json"],
}
SAVING = {
    "where --save": ["where", "B", *EVENT, "--save"],
    "compare --save": ["compare", "A", "B", *EVENT, "--max-mde-hr", "2", "--save"],
    "fix-check --save": ["fix-check", "A", "B", *EVENT, "--inputs", "all", "--max-mde", "0.5", "--save"],
    "changes --save": ["changes", "A", "B", *EVENT, "--save"],
}
WRITING = {
    **SAVING,
    "fix-check --out": ["fix-check", "A", "B", *EVENT, "--inputs", "all", "--max-mde", "0.5", "--out", "bundle"],
    "name": ["name", "B", "the newer"],
    "ui": ["ui"],
}


def argv_of(words: Sequence[str], store: Path, source: Path, by: str = "id") -> list[str]:
    """The command line: ``A`` and ``B`` written as the runs of ``source`` by id or by name, and
    ``--store`` after the verb's own words."""
    a, b = RUNS[source] if by == "id" else NAMES
    swap = {"A": a, "B": b}
    return [*[swap.get(w, w) for w in words], "--store", str(store)]


__all__ = [
    "EVENT", "FIXTURES", "IMPORT_WRITES", "INIT_READS", "JUNIT", "NAMES", "NEWER", "NOTES", "READING", "READS", "REPO", "RUNS", "SAVING",
    "STORES", "STORE_1_0", "STORE_1_2", "STORE_FORMAT", "TESTS", "WRITING", "Ran", "absent", "argv_of", "below", "copy", "cut_manifest",
    "declaring", "descriptor_file", "env_of", "home_of", "marked", "python", "refused_one_line", "run", "stating", "tree", "unversioned", "with_descriptor",
    "with_fake_prove",
]
