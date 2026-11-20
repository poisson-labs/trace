"""TF1-16: the look held over TF1's own invocations (``docs/cli-look.md``).

``runs`` and ``name`` in every form, the verbs given runs by every word, the imports TF1 refuses,
and every refusal and wrong command line TF1 adds, run in order in one folder and each held to
the same rules as TF0's corpus (``test_look_conformance``), the two clauses TF1 builds included:
the first stdout line of a result is its verdict line, and ``--json`` opens ``schema``,
``verdict``, ``sentence``."""

from __future__ import annotations

import shutil

import pytest

from conftest import TAU2
from test_look_conformance import _held
from look_support import Item, Ran, chdir, deepeval_import, run_item
from names_support import T_A, T_NAMES

S = "proofload-runs"
EV = ("--event", "unsolved")


def _corpus() -> list[Item]:
    items: list[Item] = []

    def add(label: str, command: str, argv: list[str], expect: int, kind: str) -> None:
        items.append(Item(label, command, tuple(argv), expect, kind))

    # results, in order: the names they write are read by the ones after
    add("runs", "trace", ["runs", "--store", S], 0, "report")
    add("runs with events", "trace", ["runs", "--store", S, *EV], 0, "report")
    add("runs, all, as JSON", "trace", ["runs", "--store", S, "--all", "--json"], 0, "report")
    add("name latest", "trace", ["name", "latest", "tau2 patched pilot", "--store", S], 0, "report")
    add("name by the name from the manifest", "trace", ["name", T_NAMES[T_A], "tau2 selecting run", "--store", S], 0, "report")
    add("name --list", "trace", ["name", "--list", "--store", S], 0, "report")
    add("where previous", "trace", ["where", "previous", "--store", S, *EV, "--at", "20"], 0, "report")
    add("where #3 as JSON", "trace", ["where", "#3", "--store", S, *EV, "--json"], 0, "report")
    add("compare by number", "trace", ["compare", "#3", "#2", "--store", S, *EV, "--max-mde-hr", "1.3"], 0, "report")
    add("fix-check by name", "trace", ["fix-check", "previous", "tau2 patched pilot", "--store", S, *EV, "--failing-from", "tau2 selecting run", "--max-mde", "0.2"], 0, "report")
    add("changes by target as JSON", "trace", ["changes", "previous:tau2-airline", "latest:tau2-airline", "--store", S, *EV, "--json"], 0, "report")
    add("name --forget", "trace", ["name", "tau2 patched pilot", "--forget", "--store", S], 0, "report")
    add("import, then runs on its store", "import", deepeval_import("imported", "he-a"), 0, "report")
    add("runs on imported runs", "trace", ["runs", "--store", "imported"], 0, "report")
    add("where on an imported run", "trace", ["where", "he-a", "--store", "imported", "--event", "missed"], 0, "report")
    # help
    add("runs help", "trace", ["runs", "--help"], 0, "help")
    add("name help", "trace", ["name", "--help"], 0, "help")
    # refusals
    add("an unknown name", "trace", ["where", "no such run", "--store", S, *EV], 1, "refusal")
    add("a hash fragment", "trace", ["where", "965d", "--store", S, *EV], 1, "refusal")
    add("a number past the listing", "trace", ["where", "#9", "--store", S, *EV], 1, "refusal")
    add("a target with no run", "trace", ["where", "latest:no-such-agent", "--store", S, *EV], 1, "refusal")
    add("one run twice by two words", "trace", ["fix-check", "latest", "#1", "--store", S, *EV, "--inputs", "all", "--max-mde", "0.2"], 1, "refusal")
    add("a name in use", "trace", ["name", "latest", "tau2 selecting run", "--store", S], 1, "refusal")
    add("a reserved name", "trace", ["name", "latest", "previous", "--store", S], 1, "refusal")
    add("a name too long", "trace", ["name", "latest", "x" * 81, "--store", S], 1, "refusal")
    add("a name of two lines", "trace", ["name", "latest", "a\nb", "--store", S], 1, "refusal")
    add("a name in no store", "trace", ["name", "latest", "x", "--store", "no-such-store"], 1, "refusal")
    add("runs of no store", "trace", ["runs", "--store", "no-such-store"], 1, "refusal")
    add("an import named ..", "import", deepeval_import("imported", ".."), 1, "refusal")
    add("an import named a/b", "import", deepeval_import("imported", "a/b"), 1, "refusal")
    add("an import named latest", "import", deepeval_import("imported", "latest"), 1, "refusal")
    add("an unknown name, as JSON", "trace", ["where", "no such run", "--store", S, *EV, "--json"], 1, "refusal")
    # the command line is wrong
    add("name with nothing", "trace", ["name", "--store", S], 2, "usage")
    add("name with no new name", "trace", ["name", "latest", "--store", S], 2, "usage")
    add("runs with no store", "trace", ["runs"], 2, "usage")
    add("runs with an unknown option", "trace", ["runs", "--store", S, "--newest"], 2, "usage")
    return items


CORPUS = _corpus()


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Ran]:
    work = tmp_path_factory.mktemp("tf1-corpus")
    shutil.copytree(TAU2, work / S)
    results = {}
    with chdir(work):
        for item in CORPUS:
            results[item.label] = run_item(item)
    return results


@pytest.mark.parametrize("kind", ["report", "help", "refusal", "usage"])
def test_tf1_16_the_corpus_holds_the_look(ran: dict[str, Ran], kind: str) -> None:
    broken = {item.label: _held(item, ran[item.label]) for item in CORPUS if item.kind == kind}
    broken = {label: why for label, why in broken.items() if why}
    assert broken == {}, broken
