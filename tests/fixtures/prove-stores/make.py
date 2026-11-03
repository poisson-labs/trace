"""Make the Prove store TF16's tests and the pin's tests read, ``prove-0.1.2/``, by running the
published Prove's own sweep on its keyless mock agent: poisson-prove 0.1.2 from PyPI
(``poisson-prove==0.1.2``, installed with ``pip install poisson-prove==0.1.2``). Its runs are
named at sweep time and a comparison of them is saved, so it holds the store descriptor, the event
logs and an artifact under ``.poisson/``.

usage: python make.py DEST [--python PYTHON]

PYTHON is an interpreter with that Prove installed (default: the one running this script); the
recipe refuses any other version. Nothing here calls a model or the network; the salt is fixed,
so a second run stores the same outcomes, and only the run ids, the times and the files that
carry them differ.

The other store beside it, ``prove-0.0.1/``, is not made here: it is kept as Prove wrote it in
October under its old name, ``proofload`` 0.0.1, which was never on a package index (see
PROVENANCE.md).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROVE = "0.1.2"  # poisson-prove==0.1.2, from PyPI
SALT = "5eed000000000016"


def run(python: str, *argv: str, cwd: Path) -> str:
    result = subprocess.run([python, *argv], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"{' '.join(argv)} failed ({result.returncode}):\n{result.stdout}{result.stderr}")
    return result.stdout


def prove_version(python: str) -> str:
    return run(python, "-c", "import poisson_prove; print(poisson_prove.__version__)", cwd=HERE).strip()


def store(python: str, dest: Path) -> Path:
    root = dest / f"prove-{PROVE}"
    prove = ("-m", "poisson_prove")
    where = ("--store", str(root))
    spec = str(dest / "sweep.toml")
    agent = "poisson_prove.examples.mock_agent"
    run(python, *prove, "sweep", spec, "--target", f"{agent}:rollout", "--salt", SALT,
        "--name", "agent before", "--max-mde", "0.5", "--yes", *where, cwd=dest)
    run(python, *prove, "sweep", spec, "--target", f"{agent}:rollout_patched", "--pair-with",
        "latest", "--name", "agent after", "--max-mde", "0.5", "--yes", *where, cwd=dest)
    run(python, *prove, "diff", "agent before", "agent after", "--event", "violated", "--save",
        *where, cwd=dest)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dest", type=Path)
    parser.add_argument("--python", default=sys.executable,
                        help=f"a Python with poisson-prove=={PROVE} installed from PyPI")
    ns = parser.parse_args()
    found = prove_version(ns.python)
    if found != PROVE:
        sys.exit(f"{ns.python} has poisson-prove {found}; this recipe needs {PROVE}: "
                 f"pip install poisson-prove=={PROVE}")
    dest = ns.dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        sys.exit(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "sweep.toml", dest / "sweep.toml")
    made = store(ns.python, dest)
    (dest / "sweep.toml").unlink()
    print(f"made {made}")


if __name__ == "__main__":
    main()
