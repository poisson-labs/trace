"""TF18-20 and TF18-21: nothing else moves (rule 7 of the pair's brief).

**TF18-20** Every invocation of ``tf18_support.pin_corpus()`` prints, piped, what main 4eb8c1b
printed, byte for byte: the exit code, stdout and stderr of each step. That is the failure
breakdown pair's corpus whole (every verb on each kind of store with each option, the refusals,
every reader's import, the names, the larger fixtures; plain and ``--json``), every existing
verb's ``--help``, the four counting verbs with ``--save`` (twice, and with ``--json``),
``--out`` (made, refused, forced with ``--json``), ``--svg``, and ``handover`` refusing and
finding a bundle not valid. So a save rebuilds the pages without a word on stdout or stderr
(A7), and the compare artifact's new charts change nothing a command prints (A9). Pinned by
``fixtures/tf18/make_main_pins.py``.

**TF18-21** The three outputs TF18 changes, changed exactly so: the top ``--help`` is main's with
rows for ``ui`` and ``report`` added in its verbs list and nothing else (A10); the refusals that
name the verbs name ``ui`` and ``report`` last (A11); ``handover --check`` on a valid bundle
prints main's line, a blank line and ``next: poisson-trace report DIR``, as ``name`` ends
(SB5, A12).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tf0_support import REPO
from tf13_support import workspace
from tf18_support import CHANGED, MAIN, PINS, SLOW, digest, normal, pin_corpus, run_steps

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()


def _ran(tmp: Path, place: str, kind: str, steps: list[list[str]]) -> list[tuple[int, str, str]]:
    work = workspace(tmp) if place == "work" else REPO
    return [(r.code, normal(r.out, work), normal(r.err, work)) for r in run_steps(work, place, kind, steps)]


def test_tf18_20_every_case_is_pinned_on_main() -> None:
    assert PINNED["main"] == MAIN
    assert set(PINNED["piped"]) == set(CORPUS)
    assert set(PINNED["changed"]) == set(CHANGED)


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in CORPUS])
def test_tf18_20_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    got = [[code, digest(out), digest(err)] for code, out, err in _ran(tmp_path, place, kind, steps)]
    assert got == PINNED["piped"][label], label


# ---------- TF18-21: the three that change ----------

NEW_VERBS = ("ui", "report")


def test_tf18_21_the_top_help_gains_the_two_verbs_and_nothing_else(tmp_path: Path) -> None:
    (code, out, err), = _ran(tmp_path, *CHANGED["help: top"])
    (main_code, main_out, main_err), = PINNED["changed"]["help: top"]
    assert (code, err) == (main_code, main_err)
    old, new = main_out.splitlines(), out.splitlines()
    # main's lines all there, in order
    it = iter(new)
    assert all(any(line == n for n in it) for line in old), out
    added = list(new)
    for line in old:
        added.remove(line)
    start = new.index("verbs:")
    end = new.index("examples:")
    # every added line is inside the verbs list: a verb's row or the continuation of one
    rows = [line for line in added if not line.startswith(" " * 15)]
    assert sorted(r.split()[0] for r in rows) == sorted(NEW_VERBS), added
    assert all(start < new.index(line) < end for line in added), added
    assert all(line.startswith("    ") for line in added), added


@pytest.mark.parametrize("label", ["verb: unknown", "verb: none"])
def test_tf18_21_the_verbs_named_in_a_refusal(tmp_path: Path, label: str) -> None:
    (code, out, err), = _ran(tmp_path, *CHANGED[label])
    (main_code, main_out, main_err), = PINNED["changed"][label]
    want = main_err.replace("handover, import and doctor", "handover, import, doctor, ui and report")
    assert want != main_err
    assert (code, out, err) == (main_code, main_out, want)


def test_tf18_21_handover_check_names_its_next_command(tmp_path: Path) -> None:
    made, checked = _ran(tmp_path, *CHANGED["handover: ok"])
    main_made, main_checked = PINNED["changed"]["handover: ok"]
    assert list(made) == list(main_made)
    assert checked[0] == main_checked[0] == 0 and checked[2] == main_checked[2]
    assert checked[1] == main_checked[1] + "\nnext: poisson-trace report hb\n"
