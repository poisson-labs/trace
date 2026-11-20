"""What main prints, builds and holds, pinned for the Prove label kinds tests (PL):
main as ``MAIN`` names it, with the TF20 recipe, and how each output the rule moves moves.
Not collected.
``fixtures/label-kinds/make_main_pins.py`` takes the pins with this module alone.

What is pinned, each as that main gives it:

``piped``
    TF20's whole corpus (``recipe_pins.pin_corpus()``: every verb's plain and ``--json`` output on
    each kind of store, each option, the refusals, every help, every import, a pull of each
    service, the names, the saves, ``ui`` and ``report``), and ``EXTRA``: the three verbs of two
    runs on the committed cs store and ``changes`` on tau2, whose labels the rule reads. Each
    step's exit code and the digests of its stdout and stderr.
``init``, ``setup``, ``skill``, ``pages``, ``app``
    As TF20 pins them: ``init`` on the files it finds and on a folder of every tool; ``doctor``
    and ``init`` on a store, the machine's own words written out; the setup skill; every file
    ``ui`` writes over TF19's workspace; every screen of the terminal app.
``files``, ``tracked``
    The digest of every file of the repository a user is given or reads (TF20's list), and the
    path of every file main tracks.
``texts``
    Main's text of every case the rule moves (``CHANGED``), and of ``docs/config.md``, so that a
    test can say what moved in them without the repository's history.

Paths are written ``<ROOT>``; no pin holds a path of the machine that took it.

How the rule moves an output (``CHANGED``): only ``Failures by kind`` of ``fix-check``,
``compare`` and ``changes``, and only on runs Prove swept whose failed tries carry a label with
no kind: the plain report gains one paragraph, the note (``label_kinds_support.note``), after the tries
line (and the no-outcome sentence, when there is one); ``--json`` gains
``failure_taxonomy_diff.labels_without_kind`` as its last key. Nothing else moves: the kinds,
their counts and every other byte are main's.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from label_kinds_support import CS, note
from recipe_pins import file_digest, pinned_paths as tf20_pinned, text_digest, tracked
from recipe_pins import pin_corpus as tf20_corpus

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
PL = TESTS / "fixtures" / "label-kinds"
PINS = PL / "main-pins.json"
MAIN = "c981832"

TAU2_A, TAU2_B = "20260915T210140Z-4847", "20260915T211148Z-965d"
CS_A, CS_B = "20260925T234602Z-3ea0", "20260925T235434Z-af48"
CS_EVENTS = ["--event", "forbidden_action", "--event", "unresolved", "--event", "max_turns", "--event", "app_error"]


def _cs(verb: str, *extra: str) -> list[str]:
    return [verb, CS_A, CS_B, "--store", str(CS), *CS_EVENTS, *extra]


#: The cases these tests add to the corpus: the label-bearing stores the corpus did not read with
#: every verb of two runs.
EXTRA: dict[str, tuple[str, str, list[list[str]]]] = {}
for _label, _argv in (
    ("changes cs", _cs("changes")),
    ("fix-check cs", _cs("fix-check", "--inputs", "all", "--max-mde", "0.9")),
    ("compare cs", _cs("compare", "--max-mde-hr", "9")),
    ("changes tau2", ["changes", TAU2_A, TAU2_B, "--store", str(REPO / "tests" / "fixtures" / "tau2"), "--event", "unsolved"]),
):
    EXTRA[f"labels: {_label}"] = ("repo", "trace", [_argv, [*_argv, "--json"]])

#: Every case the rule moves: the labels its note names, and each run's count of their failed
#: tries, by the key the JSON gives the run.
CHANGED: dict[str, list[dict[str, Any]]] = {
    "fixture: compare tau2": [{"label": "unsolved", "a": 110, "b": 112}],
    "fixture: fix-check tau2": [{"label": "unsolved", "old": 112, "new": 3}],
    "fixture: fix-check tau2 all": [{"label": "unsolved", "old": 110, "new": 112}],
    "fixture: fix-check humaneval": [{"label": "crashed", "old": 8, "new": 11}, {"label": "failed_assertion", "old": 1329, "new": 1376}],
    "fixture: changes humaneval": [{"label": "crashed", "a": 8, "b": 11}, {"label": "failed_assertion", "a": 1329, "b": 1376}],
    "labels: changes cs": [{"label": "forbidden_action", "a": 2, "b": 2}, {"label": "unresolved", "a": 2, "b": 2}],
    "labels: fix-check cs": [{"label": "forbidden_action", "old": 2, "new": 2}, {"label": "unresolved", "old": 2, "new": 2}],
    "labels: compare cs": [{"label": "forbidden_action", "a": 2, "b": 2}, {"label": "unresolved", "a": 2, "b": 2}],
    "labels: changes tau2": [{"label": "unsolved", "a": 110, "b": 112}],
}
#: The larger cases, slow; each kind has a fast case among the rest.
SLOW = frozenset({"fixture: compare tau2", "fixture: fix-check tau2", "fixture: fix-check tau2 all", "fixture: fix-check humaneval",
                  "fixture: changes humaneval"})
#: The files the rule changes: the five modules of the rule, and the config's page.
BUILT = ("src/poisson_trace/config.py", "src/poisson_trace/core.py", "src/poisson_trace/doctor.py",
         "src/poisson_trace/ingest/prove.py", "src/poisson_trace/ingest/taxonomy.py", "docs/config.md")
TEXT_FILES = ("docs/config.md",)


def pin_corpus() -> dict[str, tuple[str, str, list[list[str]]]]:
    out = dict(tf20_corpus())
    out.update(EXTRA)
    return out


def pin_slow() -> frozenset[str]:
    from recipe_pins import pin_slow as tf20_slow

    return tf20_slow() | SLOW


def pinned_paths(names: list[str]) -> list[str]:
    return [n for n in tf20_pinned(names) if not n.startswith("tests/fixtures/label-kinds/")]


# ---------- how a moved output moves ----------

HEADING = "## Failures by kind"
SIGNALS_LINE = "Signals seen on tries, failed or not:"


def moved_plain(text: str, labels: list[str]) -> str:
    """Main's plain report with the note after the tries line of ``Failures by kind`` (and the
    no-outcome sentence after it, when there is one)."""
    lines = text.split("\n")
    at = lines.index(HEADING)
    tries = next(i for i in range(at, len(lines)) if lines[i].endswith("; a try has one kind"))
    end = tries
    if end + 2 < len(lines) and lines[end + 1] == "" and lines[end + 2].startswith("Tries with no outcome: "):
        end += 2
    return "\n".join([*lines[:end + 1], "", note(labels), *lines[end + 1:]])


def moved_json(text: str, counts: list[dict[str, Any]]) -> str:
    doc = json.loads(text)
    assert json.dumps(doc, indent=2) + "\n" == text, "main's JSON is json.dumps(indent=2) of itself"
    doc["failure_taxonomy_diff"]["labels_without_kind"] = counts
    return json.dumps(doc, indent=2) + "\n"


def moved(label: str, main: list[list[Any]]) -> list[list[Any]]:
    """A moved case's steps, ``[code, out, err]`` each, from main's: the plain step and the
    ``--json`` step, as the rule moves them."""
    counts = CHANGED[label]
    labels = [c["label"] for c in counts]
    (code_p, out_p, err_p), (code_j, out_j, err_j) = main
    return [[code_p, moved_plain(out_p, labels), err_p], [code_j, moved_json(out_j, counts), err_j]]


#: The cases of the shared corpus (``breakdown_support.piped_corpus``, in every later family's
#: corpus since the failure breakdown) that the rule moves; another family's unchanged test holds
#: each with what the rule adds taken out (``unmoved``), and ``test_label_kinds_unchanged.py`` holds
#: what it adds.
MOVED_SHARED = frozenset(label for label in CHANGED if label.startswith("fixture: "))
NOTE_OPENING = "Trace has no kind for the label"


def unmoved_text(text: str) -> str:
    """An output with what the rule adds taken out, and nothing else: in a plain report, the
    note's paragraph (the line and the blank line before it); in ``--json``, the key
    ``failure_taxonomy_diff.labels_without_kind``."""
    try:
        doc = json.loads(text)
    except ValueError:
        doc = None
    if isinstance(doc, dict):
        diff = doc.get("failure_taxonomy_diff")
        if isinstance(diff, dict) and "labels_without_kind" in diff:
            del diff["labels_without_kind"]
            return json.dumps(doc, indent=2) + "\n"
        return text
    lines = text.split("\n")
    kept = [line for i, line in enumerate(lines)
            if not line.startswith(NOTE_OPENING) and not (line == "" and i + 1 < len(lines) and lines[i + 1].startswith(NOTE_OPENING))]
    return "\n".join(kept)


def unmoved(steps: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
    """A case's steps, each output with what the rule adds taken out."""
    return [(code, unmoved_text(out), unmoved_text(err)) for code, out, err in steps]


__all__ = ["CHANGED", "EXTRA", "MAIN", "MOVED_SHARED", "PINS", "file_digest", "pin_corpus", "pin_slow", "pinned_paths", "text_digest",
           "tracked", "unmoved"]
