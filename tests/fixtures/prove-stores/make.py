"""Make the two Prove stores TF16's tests read, by running Prove's own sweep on its keyless mock
agent: ``prove-0.0.1/`` with proofload 0.0.1 (Prove at 98dc6af) and ``prove-main/`` with
poisson-prove (Prove's main at fa31d79), the second with names given at sweep time and a saved
comparison, so it holds the store descriptor, the event logs and an artifact under ``.poisson/``.

usage: python make.py DEST --old PYTHON --new PYTHON

PYTHON is an interpreter with that Prove installed: ``--old`` imports ``proofload`` 0.0.1 and
``--new`` imports ``poisson_prove``. Nothing here calls a model or the network; the salt is fixed,
so a second run stores the same outcomes, and only the run ids, the times and the files that
carry them differ.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SALT = "5eed000000000016"


def run(python: str, *argv: str, cwd: Path) -> str:
    result = subprocess.run([python, *argv], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"{' '.join(argv)} failed ({result.returncode}):\n{result.stdout}{result.stderr}")
    return result.stdout


def old_store(python: str, dest: Path) -> None:
    store = dest / "prove-0.0.1"
    prove = ("-m", "proofload", "--store", str(store))
    spec = str(dest / "sweep.toml")
    agent = "proofload.examples.mock_agent"
    run(python, *prove, "sweep", spec, "--target", f"{agent}:rollout", "--salt", SALT,
        "--max-mde", "0.5", "--yes", cwd=dest)
    (first,) = sorted(p.name for p in store.iterdir())
    run(python, *prove, "sweep", spec, "--target", f"{agent}:rollout_patched", "--pair-with", first,
        "--max-mde", "0.5", "--yes", cwd=dest)


def new_store(python: str, dest: Path) -> None:
    store = dest / "prove-main"
    prove = ("-m", "poisson_prove")
    where = ("--store", str(store))
    spec = str(dest / "sweep.toml")
    agent = "poisson_prove.examples.mock_agent"
    run(python, *prove, "sweep", spec, "--target", f"{agent}:rollout", "--salt", SALT,
        "--name", "agent before", "--max-mde", "0.5", "--yes", *where, cwd=dest)
    run(python, *prove, "sweep", spec, "--target", f"{agent}:rollout_patched", "--pair-with",
        "latest", "--name", "agent after", "--max-mde", "0.5", "--yes", *where, cwd=dest)
    run(python, *prove, "diff", "agent before", "agent after", "--event", "violated", "--save",
        *where, cwd=dest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dest", type=Path)
    parser.add_argument("--old", required=True, help="a Python that imports proofload 0.0.1")
    parser.add_argument("--new", required=True, help="a Python that imports poisson_prove")
    ns = parser.parse_args()
    dest = ns.dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        sys.exit(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "sweep.toml", dest / "sweep.toml")
    old_store(ns.old, dest)
    new_store(ns.new, dest)
    (dest / "sweep.toml").unlink()
    print(f"made {dest / 'prove-0.0.1'} and {dest / 'prove-main'}")


if __name__ == "__main__":
    main()
