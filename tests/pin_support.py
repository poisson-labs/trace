"""The Prove that Trace reads, as the tests know it: written here once, so no test holds another.

Taylor's rulings of 2026-11-17 and 2026-11-18 (PV-2, PV-3, PV-4, PV-7): Trace declares a floor,
``poisson-prove>=0.4.0`` with no upper cap, and reads any Prove at or above it. The floor is
moved later only on purpose. It was an exact pin before: 0.1.2 by the ruling of 2026-11-03, then
0.1.3 by the ruling of 2026-11-04, the Prove that made the store ``prove-0.1.3`` and the Prove
every pin of what main prints was taken with until this floor. Moving the floor moves this file,
the one place Trace writes it, and the digests that hold them.
"""

from __future__ import annotations

import importlib.metadata
import re

#: The oldest Prove that Trace reads: the floor ``pyproject.toml`` declares.
RECORDED = "0.4.0"
REQUIREMENT = f"poisson-prove>={RECORDED}"
# the one command that installs a Prove Trace reads, from PyPI; quoted, since a shell reads ``>``
INSTALL = f'pip install "{REQUIREMENT}"'
#: How a sentence names the Proves Trace reads.
OR_LATER = f"{RECORDED} or later"

#: The Prove that made ``tests/fixtures/prove-stores/prove-0.1.3``, the store kept as the frozen
#: fixture of the stored format's 1.0 (PV-7), and the Prove every pin of what main prints was
#: taken with before the floor.
FORMAT_1_0 = "0.1.3"
#: The Prove that made ``tests/fixtures/prove-stores/prove-0.4.0``: the floor, which writes the
#: stored format's 1.2.
FORMAT_1_2 = RECORDED

# Commits of the archived Prove repository that Trace once named (its pin comment, the fixture
# recipes, the vault's notes). Written in halves so this file never holds one whole and the
# scan for them (PIN-5) reads every file, this one included.
OLD_PROVE_COMMITS = ("98dc" + "6af", "fa31" + "d79", "ff87" + "782")


def installed() -> str:
    """The version of the Prove this suite runs against, as its package states it."""
    return importlib.metadata.version("poisson-prove")


def release(version: str) -> tuple[int, ...]:
    """The numbers a version opens with, for telling one at or above the floor from one below."""
    found = re.match(r"\d+(?:\.\d+)*", version)
    assert found, version
    return tuple(int(n) for n in found.group(0).split("."))


def at_or_above_the_floor(version: str) -> bool:
    """Whether ``version`` is the floor or a later Prove, as pip orders versions: a pre-release
    of the floor itself (``0.4.0rc1``, ``0.4.0.dev1``) is below it."""
    mine, floor = release(version), release(RECORDED)
    width = max(len(mine), len(floor))
    mine, floor = mine + (0,) * (width - len(mine)), floor + (0,) * (width - len(floor))
    if mine != floor:
        return mine > floor
    return re.match(r"\d+(?:\.\d+)*(?:a|b|rc|\.?dev)\d*", version) is None


def as_pinned(text: str, found: str | None = None) -> str:
    """``text``, something Trace printed, with the version of the installed Prove written as the
    Prove the pins of main were taken with (``FORMAT_1_0``), in each place Trace prints it and
    nowhere else, so a pin of what main printed holds on any Prove at or above the floor (PV-5):

    - the ``"version"`` of a ``"prove": {...}`` object: in a verb's ``--json``, in a saved
      ``result.json`` and in ``init --json``;
    - ``"prove": ...`` among a saved result's ``versions``;
    - ``doctor``'s line, which under the floor reads ``poisson-prove X (Trace reads version
      0.4.0 or later)`` and on main read ``poisson-prove 0.1.3 (the version Trace reads)``;
    - the version line, ``(poisson-prove X, Python``;
    - ``"poisson_prove_version": ...``, the stamp Prove writes in a run's manifest;
    - a page's line of what made it, ``poisson-trace V · poisson-prove X``;
    - a figure's footer, ``Poisson Trace · Prove X ·``.

    Every other byte is left as it is. ``found`` is the installed Prove when not given."""
    now = re.escape(installed() if found is None else found)
    text = re.sub(rf'("prove":\s*\{{[^{{}}]*?"version":\s*"){now}(")', rf"\g<1>{FORMAT_1_0}\g<2>", text)
    text = re.sub(rf'("prove":\s*"){now}(")', rf"\g<1>{FORMAT_1_0}\g<2>", text)
    text = re.sub(rf'("poisson_prove_version":\s*"){now}(")', rf"\g<1>{FORMAT_1_0}\g<2>", text)
    text = re.sub(rf"poisson-prove {now} \(Trace reads version {re.escape(OR_LATER)}\)",
                  f"poisson-prove {FORMAT_1_0} (the version Trace reads)", text)
    text = re.sub(rf"\(poisson-prove {now}, Python ", f"(poisson-prove {FORMAT_1_0}, Python ", text)
    text = re.sub(rf'(poisson-trace [^\s<]+ (?:<span class="dim">\u00b7</span>|\u00b7) poisson-prove ){now}(?![\w.])', rf"\g<1>{FORMAT_1_0}", text)
    return re.sub(rf"(Poisson Trace \u00b7 Prove ){now}( \u00b7)", rf"\g<1>{FORMAT_1_0}\g<2>", text)
