"""TF5-1 to TF5-6: nothing else moves (the brief's rule 8).

**TF5-1** The pins are whole: every invocation of ``tf5_pins.pin_corpus()`` is pinned on main
2ff191b, TF26's corpus is inside it, and what main gained with the Weave reader is beside it.

**TF5-2** Every invocation of the corpus prints, piped, what main 2ff191b printed, byte for
byte: the exit code, stdout and stderr of each step. That is every verb's plain and ``--json``
output on each kind of store, each option, the refusals, every reader's help under both
spellings, every import (the three API readers' and a pull of each among them), the names, the
saves, ``ui`` and ``report``. Pinned by ``fixtures/tf5/make_main_pins.py`` on Python 3.12.13 and
checked on 3.11 too. The larger cases are slow; each has a fast twin (TF18's rule).

**TF5-3** The four things a command prints that this pair changes, changed exactly so. The
eight helps whose examples name the store folder are main's with ``proofload-runs`` written
``prove-runs`` and nothing else, and no help or refusal names the old folder any more. In the
top help, the sentence that lists the tools the import reads names all ten in the one order
where main's names four, and the first sentence says Trace reads Prove's runs and the results
the other ten tools wrote where main's says it reads the runs Prove has stored (ruled
2026-11-13, DOC-33); those two paragraphs are wrapped again, every other sentence of them is
main's, and no other paragraph moves. And the refusal of the bare command lists the verbs in
the top help's order (the same ruling), in each of the nine invocations that print it, with
nothing else of it moved; and the refusal of a word that is no verb lists them in that order
too, from the one list (ruled 2026-11-13, DOC-35). The ten cases stay in TF5-2's corpus, held
there on every other byte.

**TF5-4** The pages, as main builds them: ``ui`` over TF19's workspace writes every page file
main wrote, byte for byte once the save times are set aside, and no other.

**TF5-5** The terminal app, as main shows it: every screen over that workspace, row for row.

**TF5-6** ``init`` on the files it finds, as main prints it: LangSmith's, Braintrust's and
Weave's files (each refused with its import lines), and a folder holding a file of every tool.

**TF5-7** ``doctor`` and ``init`` on a store, which no earlier pair pinned whole because what
they print names the machine: the report and ``--json`` of each, as main prints them, with the
Python and the package's folder written out (``tf5_pins.machine``); ``doctor --setup``; and
``init --agent``, the files it writes and its refusal to write over them.

**TF5-8** The setup skill, as ``init --agent --print`` prints it: main's, line for line, but
the one step that lists the files the readers read, which names all ten tools in the one
order (B-6) and is otherwise the docs pair's to word.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tf5_pins import (
    CHANGED, EVERY_LABEL, INIT, MAIN, NEW_STORE, NO_VERB, NO_VERB_CASES, NO_VERB_MAIN, NO_VERB_NEXT, NOT_A_VERB, NOT_A_VERB_CASES, OLD_STORE, PINS, SETUP, SKILL, SKILL_STEP, TOOLS,
    TOP_FIRST, TOP_FIRST_MAIN, TOP_LIST, TOP_PARAGRAPH, TOP_SAYS, TOP_SENTENCE, VERBS_MAIN, VERBS_SAID, WEAVE, app_pins, as_main_printed, machine, pin_corpus, pin_slow,
    ran_case, ran_every_tool, ran_init, renamed,
)
from tf5_support import VERBS, WORDS, named
from tf19_support import digest, make_world, pages_pins

PINNED: dict[str, Any] = json.loads(PINS.read_text(encoding="utf-8"))
CORPUS = pin_corpus()
SLOW = pin_slow()


# ---------- TF5-1 ----------


def test_tf5_1_every_case_is_pinned_on_main() -> None:
    assert PINNED["main"] == MAIN == "2ff191b"
    assert set(PINNED["piped"]) == set(CORPUS)
    assert set(PINNED["changed"]) == set(CHANGED) and not set(CHANGED) & set(CORPUS)
    assert set(PINNED["init"]) == {*INIT, EVERY_LABEL}
    assert set(PINNED["setup"]) == set(SETUP) and len(PINNED["skill"]) == 1
    assert len(PINNED["piped"]) >= 185 and len(PINNED["pages"]) == 23 and len(PINNED["app"]) == 11
    for tool in TOOLS:
        assert f"help: import {tool}" in PINNED["piped"] and f"help: alias {tool}" in PINNED["piped"], tool
    assert set(WEAVE) <= set(PINNED["piped"])
    from tf26_pins import CHANGED as tf26_changed, pin_corpus as before

    assert set(before()) - set(CHANGED) <= set(PINNED["piped"])
    assert set(tf26_changed) - {"import refusal: weave"} <= set(PINNED["piped"])
    for label in ("langsmith: a pull", "braintrust: a pull", "weave: a pull", "refusal: an unknown event", "help: doctor", "help: handover",
                  "help: ui", "help: report"):
        assert label in PINNED["piped"], label


def test_tf5_1_no_pin_holds_a_path_of_the_machine_that_took_it() -> None:
    text = PINS.read_text(encoding="utf-8")
    for word in ("/Users/", "/home/", "/private/", "/var/folders/"):
        assert word not in text, word


def test_tf5_1_every_pinned_weave_case_runs_as_main_ran_it() -> None:
    """The exit codes main gave the Weave cases, written out: the pins hold a reader that
    worked, and each refusal is the one meant."""
    codes = {label: [step[0] for step in PINNED["piped"][label]] for label in WEAVE}
    assert codes["weave: import"] == [0, 0, 1] and codes["weave: import json"] == [0, 0]
    assert codes["weave: refusals"] == [1, 2, 2, 1, 1, 1, 1]
    assert codes["weave: a pull"] == [0, 0, 1, 0, 0]
    # where says the page's rows carry no steps; compare and the measures refuse them
    assert codes["weave: the verbs on the page's files"] == [0, 0, 0, 1, 1]
    assert all(code == 0 for label in ("weave: the verbs", "weave: import by status", "weave: import the page's files",
                                       "weave: import the paged answer", "help: import", "help: import weave") for code in codes[label])
    assert codes["import refusal: a tool not in this install"] == [1, 1]


# ---------- TF5-2 ----------


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW else k for k in CORPUS])
def test_tf5_2_as_main_prints_it(tmp_path: Path, label: str) -> None:
    place, kind, steps = CORPUS[label]
    # the two refusals that list the verbs list them in the top help's order (TF5-3 holds that); every other byte of them is main's
    moved = (*NO_VERB_CASES, *NOT_A_VERB_CASES)
    got = [[code, digest(out), digest(as_main_printed(label, err) if label in moved else err)] for code, out, err in ran_case(tmp_path, place, kind, steps)]
    assert got == PINNED["piped"][label], label


def test_tf5_2_a_fast_case_stands_for_each_slow_one() -> None:
    """The slow cases are the larger fixtures and the DeepEval import (TF18's); each kind of
    invocation among them has a case in the pull-request lane."""
    fast = [label for label in CORPUS if label not in SLOW]
    twin = {"fixture": "verb", "import": "import", "import json": "import json"}
    assert SLOW & set(CORPUS)
    for label in SLOW & set(CORPUS):
        family, _, rest = label.partition(": ")
        verb = rest.split()[0]
        assert any(other.startswith(f"{twin[family]}: ") and (family != "fixture" or verb in other) for other in fast), label


# ---------- TF5-3 ----------


@pytest.mark.parametrize("label", list(CHANGED))
def test_tf5_3_a_help_s_examples_name_the_published_prove_s_store_folder_and_nothing_else_moves(tmp_path: Path, label: str) -> None:
    (code, out, err), = ran_case(tmp_path, *CHANGED[label])
    (main_code, main_out, main_err), = PINNED["changed"][label]
    assert (main_code, main_err) == (0, "") and OLD_STORE in main_out
    assert (code, err) == (0, "")
    assert OLD_STORE not in out and NEW_STORE in out
    if label != "help: top":
        assert out == renamed(main_out), label
        return
    # the top help: every paragraph main's but the first and the one that lists the tools the import reads
    ours, mains = out.split("\n\n"), renamed(main_out).split("\n\n")
    assert len(ours) == len(mains)
    (at,) = [i for i, paragraph in enumerate(mains) if paragraph.startswith(TOP_PARAGRAPH)]
    (first,) = [i for i, paragraph in enumerate(mains) if paragraph.startswith(TOP_FIRST)]
    assert first < at and mains[first] == TOP_FIRST_MAIN
    assert [p for i, p in enumerate(ours) if i not in (first, at)] == [p for i, p in enumerate(mains) if i not in (first, at)], "no other paragraph moves"
    # the first paragraph: its first sentence says what Trace reads, all of it; the rest is main's, wrapped again
    opening, main_opening = " ".join(ours[first].split()), " ".join(mains[first].split())
    assert main_opening.startswith(TOP_SENTENCE + " ") and TOP_SENTENCE not in opening
    sentence, rest = opening[:opening.index(TOP_SAYS) + len(TOP_SAYS)], opening[opening.index(TOP_SAYS) + len(TOP_SAYS):]
    assert rest == main_opening[len(TOP_SENTENCE):], "every other sentence of the first paragraph is main's"
    reads = sentence[:-len(TOP_SAYS)]
    assert reads.startswith(TOP_FIRST) and reads.count(".") == 0, "one sentence"
    assert re.search(r"\bProve\b", reads) and re.search(r"\bruns\b", reads), "it reads Prove's runs"
    assert re.search(r"\bresults\b", reads) and re.search(r"\bten\b[^.]*\btools\b", reads), "and the results the other ten tools wrote"
    assert not re.search(r"(?i)\bonly\b", reads) and reads.rstrip().endswith("and"), reads
    assert max(len(line) for line in ours[first].split("\n")) <= max(len(line) for line in main_out.split("\n"))
    assert TOP_LIST in " ".join(mains[at].split())
    said = " ".join(ours[at].split())
    listed = re.search(r"\(([^)]*)\)", said)
    assert listed is not None and named(listed.group(1)) == list(WORDS), said
    assert said.replace(listed.group(0), TOP_LIST) == " ".join(mains[at].split()), "the sentence is main's, with the list made whole"
    assert max(len(line) for line in ours[at].split("\n")) <= max(len(line) for line in main_out.split("\n"))


@pytest.mark.parametrize("label", NO_VERB_CASES)
def test_tf5_3_the_bare_command_s_refusal_lists_the_verbs_in_the_top_help_s_order(tmp_path: Path, label: str) -> None:
    (code, out, err), = ran_case(tmp_path, *CORPUS[label])
    assert (code, out, err) == (2, "", f"{NO_VERB}\n{NO_VERB_NEXT}\n")
    assert [code, digest(out), digest(f"{NO_VERB_MAIN}\n{NO_VERB_NEXT}\n")] == PINNED["piped"][label][0], "main's, but for the order"


def test_tf5_3_that_order_is_the_top_help_s(tmp_path: Path) -> None:
    (_, out, _), = ran_case(tmp_path, *CHANGED["help: top"])
    lines = out.splitlines()
    listed = [line.split()[0] for line in lines[lines.index("verbs:") + 2:lines.index("examples:")] if re.match(r"^    \S", line)]
    assert tuple(listed) == VERBS
    assert NO_VERB.endswith(" " + ", ".join(VERBS[:-1]) + " and " + VERBS[-1])
    assert sorted(re.split(r", | and ", NO_VERB_MAIN.split(" are ")[1])) == sorted(VERBS) and NO_VERB_MAIN != NO_VERB, "the same twelve verbs"


@pytest.mark.parametrize("label", NOT_A_VERB_CASES)
def test_tf5_3_the_refusal_of_a_word_that_is_no_verb_lists_them_in_that_order_too(tmp_path: Path, label: str) -> None:
    (code, out, err), = ran_case(tmp_path, *CORPUS[label])
    first, *rest = err.splitlines()
    assert code == 2 and out == "" and rest == [NO_VERB_NEXT]
    assert first.endswith(NOT_A_VERB + VERBS_SAID) and NO_VERB.endswith(" the verbs are " + VERBS_SAID), "one list, in the top help's order"
    assert [code, digest(out), digest(err.replace(VERBS_SAID, VERBS_MAIN))] == PINNED["piped"][label][0], "main's, but for the order"


def test_tf5_3_the_examples_that_named_the_folder_are_the_eleven_of_main() -> None:
    lines = [line for label in CHANGED for line in PINNED["changed"][label][0][1].splitlines() if OLD_STORE in line]
    assert len(lines) == 11 and all(line.lstrip().startswith(("poisson-trace ", "'poisson-trace ")) or "--store proofload-runs" in line for line in lines), lines
    assert all(f"--store {OLD_STORE}" in line for line in lines)


def test_tf5_3_no_text_the_package_can_print_names_the_old_folder() -> None:
    from tf3_support import src_files

    hits = [(path.name, n) for path in src_files() for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if OLD_STORE in line]
    assert hits == []


# ---------- TF5-4 ----------


def test_tf5_4_the_pages_as_main_builds_them(tmp_path: Path) -> None:
    assert pages_pins(make_world(tmp_path)) == PINNED["pages"]


# ---------- TF5-5 ----------


def test_tf5_5_the_app_as_main_shows_it(tmp_path: Path) -> None:
    got = app_pins(make_world(tmp_path))
    assert sorted(got) == sorted(PINNED["app"])
    for screen, text in PINNED["app"].items():
        assert got[screen] == text, screen


# ---------- TF5-6 ----------


@pytest.mark.parametrize("label", list(INIT))
def test_tf5_6_init_on_the_files_it_finds_as_main_prints_it(tmp_path: Path, label: str) -> None:
    holds, steps = INIT[label]
    got = [list(step) for step in ran_init(tmp_path, holds, steps)]
    assert got == PINNED["init"][label], label


def test_tf5_6_init_on_a_file_of_every_tool_as_main_prints_it(tmp_path: Path) -> None:
    got = [list(step) for step in ran_every_tool(tmp_path)]
    assert got == PINNED["init"][EVERY_LABEL]


# ---------- TF5-7 ----------


@pytest.mark.parametrize("label", list(SETUP))
def test_tf5_7_doctor_and_init_as_main_print_them(tmp_path: Path, label: str) -> None:
    got = [[code, machine(out), machine(err)] for code, out, err in ran_case(tmp_path, *SETUP[label])]
    assert got == PINNED["setup"][label], label


def test_tf5_7_the_pins_hold_a_setup_that_worked() -> None:
    codes = {label: [step[0] for step in steps] for label, steps in PINNED["setup"].items()}
    assert codes["doctor: a config"] == [0, 0] and codes["doctor: no config"] == [4, 4] and codes["doctor: setup"] == [0, 0]
    assert codes["init: a store"] == [0, 0, 0, 1, 0] and codes["init: the agent's files"] == [0, 1, 0]
    report = PINNED["setup"]["doctor: a config"][0][1]
    assert "  python    <PYTHON>\n  package   poisson-trace " in report and "<PACKAGE>\n" in report
    assert report.startswith("ok  this environment is ready\n")


# ---------- TF5-8 ----------


def test_tf5_8_the_setup_skill_is_main_s_but_its_list_of_readers(tmp_path: Path) -> None:
    (code, out, err), = ran_case(tmp_path, *SKILL)
    (main_code, main_out, main_err), = PINNED["skill"]
    assert (code, err) == (main_code, main_err) == (0, "")
    ours, mains = out.split("\n"), main_out.split("\n")
    assert len(ours) == len(mains)
    (at,) = [i for i, line in enumerate(mains) if line.startswith(SKILL_STEP)]
    assert ours[:at] == mains[:at] and ours[at + 1:] == mains[at + 1:], "no other line of the skill moves"
    assert ours[at].startswith(SKILL_STEP)
    kept = [word for word in named(ours[at]) if word != "table"]
    assert set(named(ours[at])) == set(WORDS) and kept == [word for word in WORDS if word != "table"], named(ours[at])
