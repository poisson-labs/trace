"""PACE-10 to PACE-13: nothing else moves (the brief's rule 6). The pacing fix changes only the
times written in a run's ``events.jsonl``; every verb's plain and ``--json`` output, ``init``'s,
the pages and the terminal app stay byte for byte as main 2ff191b prints them.

**PACE-10** Every invocation of ``pacing_pins.pin_corpus()`` prints, piped, what main 2ff191b
printed, byte for byte: the exit code, stdout and stderr of each step. That is TF26's corpus
whole, TF26's three changed invocations as main now prints them, and what main gained with the
Weave reader: its help under both spellings, its imports of each kind of export in text and
``--json``, the verbs over two imported versions, its refusals, and a pull through TF26's
transport. Pinned by ``fixtures/pacing/make_main_pins.py`` on Python 3.12.13, checked on 3.11.

**PACE-11** ``init`` on the files it finds (TF26's six folders, each with and without its
imports), as main printed it.

**PACE-12** The pages, as main builds them: ``ui`` over TF19's workspace writes every page file
main wrote, byte for byte once the save times are set aside, and no other.

**PACE-13** The terminal app, as main shows it: every screen over that workspace, row for row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pacing_pins import MAIN, PINS, READERS, WEAVE, app_pins, digest_steps, init_corpus, pin_corpus, pin_slow, ran_case, ran_init
from tf19_support import make_world, pages_pins

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()
INIT = init_corpus()
SLOW = pin_slow()


# ---------- PACE-10 ----------


def test_pace_10_every_case_is_pinned_on_main() -> None:
    assert PINNED["main"] == MAIN == "2ff191b"
    assert set(PINNED["piped"]) == set(CORPUS) and len(CORPUS) >= 193
    assert set(PINNED["init"]) == set(INIT) and len(INIT) == 6
    assert len(PINNED["pages"]) >= 23 and len(PINNED["app"]) >= 11
    for tool in READERS:
        assert f"help: import {tool}" in PINNED["piped"] and f"help: alias {tool}" in PINNED["piped"], tool
    assert {"help: import", "import refusal: a tool not in this install", "import refusal: weave"} <= set(PINNED["piped"])
    assert set(WEAVE) <= set(PINNED["piped"])
    from tf26_pins import pin_corpus as before

    assert set(before()) <= set(PINNED["piped"])


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in CORPUS])
def test_pace_10_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    assert digest_steps(ran_case(tmp_path, place, kind, steps)) == PINNED["piped"][label], label


def test_pace_10_a_fast_case_stands_for_each_slow_one() -> None:
    """The slow cases are the larger fixtures and the DeepEval import (TF18's); each kind of
    invocation among them has a case in the pull-request lane."""
    fast = [label for label in CORPUS if label not in SLOW]
    twin = {"fixture": "verb", "import": "import", "import json": "import json"}
    assert SLOW & set(CORPUS)
    for label in SLOW & set(CORPUS):
        family, _, rest = label.partition(": ")
        verb = rest.split()[0]
        assert any(other.startswith(f"{twin[family]}: ") and (family != "fixture" or verb in other) for other in fast), label


def test_pace_10_every_pinned_weave_case_runs_as_main_ran_it() -> None:
    """The exit codes main gave the Weave cases, written out: the pins hold a reader that worked,
    and each refusal is the one meant."""
    codes = {label: [step[0] for step in PINNED["piped"][label]] for label in WEAVE}
    assert codes["weave: import"] == [0, 0, 1] and codes["weave: import json"] == [0, 0]
    assert codes["weave: refusals"] == [1, 2, 2, 1, 1, 1]
    assert codes["weave: a pull"] == [0, 0, 1, 0, 0]
    assert all(code == 0 for label in ("help: import weave", "help: alias weave", "weave: the verbs", "weave: import by status",
                                       "weave: import the page's files", "weave: import the paged pull") for code in codes[label])


# ---------- PACE-11 ----------


@pytest.mark.parametrize("label", list(INIT))
def test_pace_11_init_as_main_prints_it(tmp_path: Path, label: str) -> None:
    holds, steps = INIT[label]
    assert digest_steps(ran_init(tmp_path, holds, steps)) == PINNED["init"][label], label


# ---------- PACE-12 ----------


def test_pace_12_the_pages_as_main_builds_them(tmp_path: Path) -> None:
    assert pages_pins(make_world(tmp_path)) == PINNED["pages"]


# ---------- PACE-13 ----------


def test_pace_13_the_app_as_main_shows_it(tmp_path: Path) -> None:
    got = app_pins(make_world(tmp_path))
    assert sorted(got) == sorted(PINNED["app"])
    for screen, text in PINNED["app"].items():
        assert got[screen] == text, screen
