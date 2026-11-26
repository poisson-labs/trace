"""PL-50 to PL-57: nothing else moves. The pins are main's (``label_kinds_pins.MAIN``), taken by
``fixtures/label-kinds/make_main_pins.py`` on main without the rule (see ``label_kinds_pins``'s opening for
what each section holds).

- PL-50: the pins are whole, and none holds a path of the machine that took it.
- PL-51: every invocation of the corpus that the rule does not move prints, piped, what main
  printed, byte for byte: every verb's plain and ``--json`` output, every help, import, refusal,
  pull, name, save, ``ui`` and ``report``. The larger cases are slow; each kind has a fast case.
- PL-52: every case the rule moves (``label_kinds_pins.CHANGED``) prints main's output with the note
  after its tries line in plain and ``labels_without_kind`` last in its ``failure_taxonomy_diff``
  in ``--json``, and nothing else moved; the counts are those the committed stores' labels give.
- PL-53: ``init`` on the files it finds and on a folder of every tool, as main prints it.
- PL-54: ``doctor`` and ``init`` on a store (the machine's own words written out), and the setup
  skill, as main prints them.
- PL-55: the pages ``ui`` writes, and the terminal app's screens, as main gives them.
- PL-57: ``unmoved``, which other families' unchanged tests use, takes out what the rule adds
  and nothing else.
"""

from __future__ import annotations

import difflib
import json
from typing import Any

import pytest
from label_kinds_pins import CHANGED, EXTRA, MAIN, MOVED_SHARED, PINS, BUILT, moved, pin_corpus, pin_slow, unmoved
from label_kinds_support import note
from docs_pins import app_pins, machine, ran_case, ran_every_tool, ran_init
from app_support import make_world, pages_pins
from recipe_pins import EVERY_LABEL, INIT, SETUP, SKILL, digest_text_steps

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()
SLOW = pin_slow()


def _param(label: str) -> Any:
    return pytest.param(label, marks=pytest.mark.slow) if label in SLOW else label


# ---------- PL-50 ----------


def test_pl_50_the_pins_are_whole() -> None:
    assert PINNED["main"] == MAIN == "5f110d8" and PINNED["python"] == "3.12.13"
    assert set(PINNED["piped"]) == set(CORPUS) and len(CORPUS) >= 198
    assert set(EXTRA) <= set(CORPUS) and set(CHANGED) <= set(CORPUS)
    assert set(PINNED["init"]) == {*INIT, EVERY_LABEL} and set(PINNED["setup"]) == set(SETUP) and len(PINNED["skill"]) == 1
    assert len(PINNED["pages"]) == 23 and len(PINNED["app"]) == 11
    assert set(PINNED["texts"]["piped"]) == set(CHANGED) and set(PINNED["texts"]["files"]) == {"docs/config.md"}
    names = set(PINNED["files"])
    assert len(names) >= 1000 and set(BUILT) <= names and "docs/recipes/with-tasks-and-prove.md" in names
    assert not any(n.startswith("tests/fixtures/label-kinds/") for n in names)


def test_pl_50_no_pin_holds_a_path_of_the_machine_that_took_it() -> None:
    text = PINS.read_text(encoding="utf-8")
    for word in ("/Users/", "/home/", "/private/", "/var/folders/", "/tmp/"):
        assert word not in text, word


def test_pl_50_the_texts_are_the_pinned_outputs() -> None:
    for label, steps in PINNED["texts"]["piped"].items():
        assert digest_text_steps([tuple(s) for s in steps]) == PINNED["piped"][label], label
    for name, text in PINNED["texts"]["files"].items():
        from recipe_pins import text_digest

        assert text_digest(text) == PINNED["files"][name], name


# ---------- PL-51 ----------


@pytest.mark.parametrize("label", [_param(k) for k in CORPUS if k not in CHANGED])
def test_pl_51_as_main_prints_it(tmp_path: Any, label: str) -> None:
    place, kind, steps = CORPUS[label]
    assert digest_text_steps(ran_case(tmp_path, place, kind, steps)) == PINNED["piped"][label], label


def test_pl_51_a_fast_case_stands_for_each_slow_one() -> None:
    fast = [label for label in CORPUS if label not in SLOW]
    twin = {"fixture": "verb", "import": "import", "import json": "import json"}
    for label in SLOW & set(CORPUS):
        family, _, rest = label.partition(": ")
        verb = rest.split()[0]
        assert any(other.startswith(f"{twin[family]}: ") and (family != "fixture" or verb in other) for other in fast), label


# ---------- PL-52 ----------


@pytest.mark.parametrize("label", [_param(k) for k in CHANGED])
def test_pl_52_each_moved_output_moves_as_the_rule_says(tmp_path: Any, label: str) -> None:
    place, kind, steps = CORPUS[label]
    got = [list(s) for s in ran_case(tmp_path, place, kind, steps)]
    assert got == moved(label, PINNED["texts"]["piped"][label]), label


@pytest.mark.parametrize("label", list(CHANGED))
def test_pl_52_each_move_is_one_paragraph_and_one_key(label: str) -> None:
    main = PINNED["texts"]["piped"][label]
    new = moved(label, main)
    plain_main, plain_new = main[0][1].split("\n"), new[0][1].split("\n")
    ops = [op for op in difflib.SequenceMatcher(a=plain_main, b=plain_new, autojunk=False).get_opcodes() if op[0] != "equal"]
    assert len(ops) == 1 and ops[0][0] == "insert", ops
    _, _, _, j1, j2 = ops[0]
    assert plain_new[j1:j2] in (["", note([c["label"] for c in CHANGED[label]])], [note([c["label"] for c in CHANGED[label]]), ""])
    doc_main, doc_new = json.loads(main[1][1]), json.loads(new[1][1])
    diff = doc_new["failure_taxonomy_diff"]
    assert list(diff)[-1] == "labels_without_kind" and diff.pop("labels_without_kind") == CHANGED[label]
    assert doc_new == doc_main
    assert [main[0][0], main[0][2], main[1][0], main[1][2]] == [new[0][0], new[0][2], new[1][0], new[1][2]]


def test_pl_52_the_counts_are_the_stores_own() -> None:
    """Each count is the store's failed tries with that label the built-in rules leave
    unclassified, as ``test_label_kinds_reader.MAIN_KINDS`` holds them from main."""
    from test_label_kinds_reader import MAIN_KINDS

    def n(store: str, run: str, label: str) -> int:
        return MAIN_KINDS[(store, run)].get((label, "unclassified_error"), 0)

    tau2 = {"a": "20260915T210140Z-4847", "b": "20260915T211148Z-965d", "pilot": "20260917T140219Z-2b2d"}
    he = ("20260905T185407Z-0313", "20260905T195009Z-18ac")
    cs = ("20260925T234602Z-3ea0", "20260925T235434Z-af48")
    want = {
        "fixture: compare tau2": [{"label": "unsolved", "a": n("tau2", tau2["a"], "unsolved"), "b": n("tau2", tau2["b"], "unsolved")}],
        "fixture: fix-check tau2": [{"label": "unsolved", "old": n("tau2", tau2["b"], "unsolved"), "new": n("tau2", tau2["pilot"], "unsolved")}],
        "fixture: fix-check tau2 all": [{"label": "unsolved", "old": n("tau2", tau2["a"], "unsolved"), "new": n("tau2", tau2["b"], "unsolved")}],
        "fixture: fix-check humaneval": [{"label": x, "old": n("humaneval", he[0], x), "new": n("humaneval", he[1], x)}
                                         for x in ("crashed", "failed_assertion")],
        "fixture: changes humaneval": [{"label": x, "a": n("humaneval", he[0], x), "b": n("humaneval", he[1], x)}
                                       for x in ("crashed", "failed_assertion")],
        "labels: changes cs": [{"label": x, "a": n("cs", cs[0], x), "b": n("cs", cs[1], x)} for x in ("forbidden_action", "unresolved")],
        "labels: fix-check cs": [{"label": x, "old": n("cs", cs[0], x), "new": n("cs", cs[1], x)} for x in ("forbidden_action", "unresolved")],
        "labels: compare cs": [{"label": x, "a": n("cs", cs[0], x), "b": n("cs", cs[1], x)} for x in ("forbidden_action", "unresolved")],
        "labels: changes tau2": [{"label": "unsolved", "a": n("tau2", tau2["a"], "unsolved"), "b": n("tau2", tau2["b"], "unsolved")}],
    }
    assert CHANGED == want


def test_pl_52_the_shared_cases_it_moves() -> None:
    assert MOVED_SHARED == {"fixture: compare tau2", "fixture: fix-check tau2", "fixture: fix-check tau2 all",
                            "fixture: fix-check humaneval", "fixture: changes humaneval"}


# ---------- PL-53 ----------


@pytest.mark.parametrize("label", list(INIT))
def test_pl_53_init_on_the_files_it_finds(tmp_path: Any, label: str) -> None:
    holds, steps = INIT[label]
    assert digest_text_steps(ran_init(tmp_path, holds, steps)) == PINNED["init"][label]


def test_pl_53_init_on_a_file_of_every_tool(tmp_path: Any) -> None:
    assert digest_text_steps(ran_every_tool(tmp_path)) == PINNED["init"][EVERY_LABEL]


# ---------- PL-54 ----------


@pytest.mark.parametrize("label", list(SETUP))
def test_pl_54_doctor_and_init_on_a_store(tmp_path: Any, label: str) -> None:
    got = [(code, machine(out), machine(err)) for code, out, err in ran_case(tmp_path, *SETUP[label])]
    assert digest_text_steps(got) == PINNED["setup"][label], label


def test_pl_54_the_setup_skill(tmp_path: Any) -> None:
    assert digest_text_steps(ran_case(tmp_path, *SKILL)) == PINNED["skill"]


# ---------- PL-55 ----------


def test_pl_55_the_pages(tmp_path: Any) -> None:
    assert pages_pins(make_world(tmp_path)) == PINNED["pages"]


def test_pl_55_the_app(tmp_path: Any) -> None:
    assert app_pins(make_world(tmp_path)) == PINNED["app"]


# ---------- PL-57 ----------


@pytest.mark.parametrize("label", list(CHANGED))
def test_pl_57_unmoved_takes_out_what_the_rule_adds(label: str) -> None:
    main = [tuple(s) for s in PINNED["texts"]["piped"][label]]
    new = [tuple(s) for s in moved(label, PINNED["texts"]["piped"][label])]
    assert unmoved(new) == main  # type: ignore[arg-type]
    assert unmoved(main) == main  # type: ignore[arg-type]


def test_pl_57_unmoved_takes_out_nothing_else() -> None:
    text = "## Failures by kind\n\nTrace has no kind for nothing\n\nTrace counts the labels\n"
    assert unmoved([(0, text, "")]) == [(0, text, "")]
    doc = '{\n  "failure_taxonomy_diff": {\n    "kinds": []\n  },\n  "labels_without_kind": []\n}\n'
    assert unmoved([(0, doc, "")]) == [(0, doc, "")]
