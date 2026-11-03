"""The Prove that Trace pins, as the tests know it: written here once, so no test holds another.

Taylor's ruling of 2026-11-03: Trace pins exactly the newest ``poisson-prove`` on PyPI at the
start of the session that froze these tests, as a declared dependency, and the pin is moved later
only on purpose, as Prove work lands. ``pip index versions poisson-prove`` at 2026-11-03 14:49
UTC listed 0.1.2, 0.1.1 and 0.1.0, so the recorded version is 0.1.2. Moving the pin moves this
file, the one place Trace writes it, and the digests that hold them.
"""

from __future__ import annotations

RECORDED = "0.1.2"
REQUIREMENT = f"poisson-prove=={RECORDED}"
# the one command that installs the Prove Trace reads, from PyPI
INSTALL = f"pip install {REQUIREMENT}"

# Commits of the archived Prove repository that Trace once named (its pin comment, the fixture
# recipes, the vault's notes). Written in halves so this file never holds one whole and the
# scan for them (PIN-5) reads every file, this one included.
OLD_PROVE_COMMITS = ("98dc" + "6af", "fa31" + "d79", "ff87" + "782")
