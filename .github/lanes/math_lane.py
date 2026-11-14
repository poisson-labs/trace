"""Say whether the math lane runs for this event: `python .github/lanes/math_lane.py [BASE]`.

The math lane is the statistics' slow checks against their references (`-m math`). It always
runs on a push and on the nightly schedule. On a pull request it runs when the pull request
could have moved a statistic:

- it changes the statistics code, or a test of the math suite;
- it changes what the package depends on, or the versions the lanes were last green with;
- or the numerical packages this environment resolved are not the versions the lanes were last
  green with.

BASE is the commit the pull request branches from. Run it with the Python the lane will run on,
after the install. It prints why, and writes `run=true` or `run=false` to the file
`GITHUB_OUTPUT` names. Standard library only.
"""

from __future__ import annotations

import importlib.metadata
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: The statistics code: a change under any of these runs the lane.
STATISTICS = (
    "src/poisson_trace/paired.py",
    "src/poisson_trace/survival.py",
    "src/poisson_trace/stats",
)
#: Where a dependency is declared, and where the versions the lanes were green with are kept.
DECLARED = ("pyproject.toml", ".github/release/")
#: The numerical packages a statistic's last digits depend on.
PACKAGES = ("numpy", "scipy", "pandas", "lifelines")
#: How a test file says it is of the math suite.
MATH_MARK = "mark.math"


def changed(base: str) -> list[str]:
    """The files that differ between the pull request's base and this commit."""
    done = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )  # fmt: skip
    return [line for line in done.stdout.splitlines() if line.strip()]


def recorded() -> dict[str, str]:
    """The versions the lanes were last green with on this Python, by package; empty when no
    file records them for it."""
    name = f"lanes-{sys.version_info.major}.{sys.version_info.minor}.txt"
    path = ROOT / ".github" / "release" / name
    if not path.is_file():
        return {}
    found = re.findall(r"(?m)^([A-Za-z0-9_.-]+)==(\S+)$", path.read_text(encoding="utf-8"))
    return {package.lower(): version for package, version in found}


def reasons(event: str, base: str | None) -> list[str]:
    if event != "pull_request":
        return [f"the event is {event or 'not a pull request'}"]
    out = []
    for path in changed(base) if base else []:
        if path.startswith(STATISTICS):
            out.append(f"{path} is statistics code")
        elif path.startswith(DECLARED):
            out.append(f"{path} declares or records what is installed")
        elif path.startswith("tests/") and path.endswith(".py"):
            file = ROOT / path
            if file.is_file() and MATH_MARK in file.read_text(encoding="utf-8"):
                out.append(f"{path} is a test of the math suite")
    green = recorded()
    for package in PACKAGES:
        installed = importlib.metadata.version(package)
        if green.get(package) != installed:
            was = green.get(package, "not recorded")
            out.append(f"{package} resolved to {installed}; the lanes were green with {was}")
    return out


def main(argv: list[str]) -> int:
    why = reasons(os.environ.get("GITHUB_EVENT_NAME", ""), argv[0] if argv else None)
    run = "true" if why else "false"
    print(f"math lane: run={run}")
    for line in why:
        print(f"  {line}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as out:
            out.write(f"run={run}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
