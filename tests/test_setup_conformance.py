"""TF2-22: the look held over TF2's own invocations, and plain words in all they print.

``init`` and ``doctor`` in their forms, the verbs reading the config, and every refusal and wrong
command line TF2 adds, run in order in one folder and each held to the rules of TF0's corpus
(``test_look_conformance``): the exit code the invocation calls for; no traceback; nothing on stdout
for a refusal; one strict JSON document opening ``schema``, ``verdict``, ``sentence``; a result's
first stdout line a verdict line and ``next:`` closing it. ``init``'s questions and its listing are
progress on stderr, so stderr is held to the error and note shape only where
``init`` is not running. A not-ready ``doctor`` exits 4 and its ``--json`` is the same strict
document. Nothing any of them prints holds an internal id or a word only the lab uses."""

from __future__ import annotations

import json

import pytest

from conftest import TAU2
from test_look_conformance import _held
from look_support import Item, Ran, chdir, plain, run_item
from setup_support import config_of, scratch_home  # noqa: F401

S = "proofload-runs"


def _corpus() -> list[Item]:
    items: list[Item] = []

    def add(label: str, argv: list[str], expect: int, kind: str) -> None:
        items.append(Item(label, "trace", tuple(argv), expect, kind))

    add("init", ["init", "--yes"], 0, "report")
    add("init again, as JSON", ["init", "--yes", "--force", "--names", "from=date", "--json"], 0, "report")
    add("init adds a store", ["init", "--add-store", "second"], 0, "report")
    add("runs from the config", ["runs"], 0, "report")
    add("where from the config", ["where", "previous", "--at", "20"], 0, "report")
    add("fix-check from the config", ["fix-check", "#3", "#2", "--inputs", "all", "--max-mde", "0.2"], 0, "report")
    add("where in a named store", ["where", "latest", "--store", "second", "--json"], 0, "report")
    add("doctor", ["doctor"], 0, "report")
    add("doctor as JSON", ["doctor", "--json"], 0, "report")
    add("init help", ["init", "--help"], 0, "help")
    add("doctor help", ["doctor", "--help"], 0, "help")
    add("doctor on a config whose store is not there", ["doctor", "--config", "lost.toml"], 4, "check")
    add("doctor on it as JSON", ["doctor", "--config", "lost.toml", "--json"], 4, "check")
    add("init over a config", ["init", "--yes"], 1, "refusal")
    add("init on no store", ["init", "--yes", "--force", "--store", "no-such-store"], 1, "refusal")
    add("a config file that is not there", ["--config", "no-such.toml", "where", "previous"], 1, "refusal")
    add("a config that is not one", ["where", "previous", "--config", "wrong.toml"], 1, "refusal")
    add("a config that is not one, as JSON", ["where", "previous", "--config", "wrong.toml", "--json"], 1, "refusal")
    add("add a store with no config", ["init", "--add-store", S, "--config", "none.toml"], 1, "refusal")
    add("init with a names form not among them", ["init", "--yes", "--names", "from=model"], 2, "usage")
    add("init with an unknown option", ["init", "--yes", "--bogus"], 2, "usage")
    add("doctor with an unknown option", ["doctor", "--bogus"], 2, "usage")
    add("where with no events anywhere", ["where", "previous", "--config", "no-events.toml"], 2, "usage")
    return items


CORPUS = _corpus()


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Ran]:
    import os
    import shutil

    work = tmp_path_factory.mktemp("tf2-corpus")
    home = tmp_path_factory.mktemp("tf2-home")
    shutil.copytree(TAU2, work / S)
    shutil.copytree(TAU2, work / "second")
    (work / "lost.toml").write_text(config_of("nowhere"), encoding="utf-8")
    (work / "wrong.toml").write_text(config_of(S).replace("failed", "faild"), encoding="utf-8")
    (work / "no-events.toml").write_text(f'version = 1\n\n[store]\npath = "{S}"\n', encoding="utf-8")
    held = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    results = {}
    try:
        with chdir(work):
            for item in CORPUS:
                results[item.label] = run_item(item)
    finally:
        if held is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = held
    return results


def _broken(item: Item, result: Ran) -> list[str]:
    broken = _held(item, result)
    if item.argv[0] == "init":
        # the setup's listing is progress on stderr, and may come before an error line
        broken = [b for b in broken if not b.startswith(("stderr lines that are not", "a refusal that does not open"))]
        lines = result.lines()
        errors = [i for i, line in enumerate(lines) if line.startswith("error: ")]
        if result.code in (1, 2) and (len(errors) != 1 or not all(line.startswith("  next: ") for line in lines[errors[0] + 1 :])):
            broken.append("not one error line with only next lines under it")
    if item.kind == "check":
        if "--json" in item.argv:
            try:
                doc = json.loads(result.out)
            except ValueError as e:
                broken.append(f"--json is not one strict document: {e}")
            else:
                if list(doc)[:3] != ["schema", "verdict", "sentence"]:
                    broken.append("--json does not open with schema, verdict and sentence")
    return broken


@pytest.mark.parametrize("kind", ["report", "help", "check", "refusal", "usage"])
def test_tf2_22_the_corpus_holds_the_look(ran: dict[str, Ran], kind: str) -> None:
    broken = {item.label: _broken(item, ran[item.label]) for item in CORPUS if item.kind == kind}
    broken = {label: why for label, why in broken.items() if why}
    assert broken == {}, broken


def test_tf2_22_everything_printed_is_in_plain_words(ran: dict[str, Ran]) -> None:
    # the words read are those of the results, not of refusals in their place
    assert {item.label for item in CORPUS if item.kind == "report" and ran[item.label].code != 0} == set()
    hits = {label: plain(result.text) for label, result in ran.items() if plain(result.text)}
    assert hits == {}, hits
