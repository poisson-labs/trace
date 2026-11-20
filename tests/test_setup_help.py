"""TF2-21: help a stranger can act on for ``init`` and ``doctor``.

Each has a description, help on every argument with its default or "no default", and an example;
every example runs as written, read as a shell reads it, in a folder that holds what it names: a
copy of the tau2 store under each store path the example names (``proofload-runs`` when it names
none), and for ``doctor`` a config naming it. An ``init`` example that asks questions runs on a
terminal with Enter for every answer. ``init``'s help lists every flag ``init`` takes, and the
main help lists both verbs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from look_support import VERDICT_LINE, help_blocks, help_entries, trace
from names_support import shell_words, tau2_copy
from setup_support import CONFIG, config_of, here, scratch_home, tty, work, write_config  # noqa: F401

INIT_FLAGS = ("--store", "--add-store", "--event", "--names", "--import", "--no-import", "--max-mde", "--max-mde-hr",
              "--fail-on", "--force", "--config", "--yes", "--json")


def _help(words: list[str]) -> str:
    result = trace([*words, "--help"])
    assert result.code == 0 and result.err == "", result.text
    return result.out


@pytest.mark.parametrize("verb", ["init", "doctor"])
def test_tf2_21_the_help_is_a_strangers(verb: str) -> None:
    text = _help([verb])
    blocks = help_blocks(text)
    assert blocks[0].startswith("usage:")
    assert len(blocks[1].split()) >= 8 and "." in blocks[1] and not re.match(r"^\S[^\n]*:\n", blocks[1] + "\n"), blocks[1]
    entries = help_entries(text)
    assert entries, text
    for invocation, words in entries:
        if invocation.startswith("-h, --help"):
            continue
        assert words, f"{invocation} has no help text"
        if invocation.startswith("-") and " " in invocation.split(",")[-1].strip():
            assert "default" in words, f"{invocation}: {words}"
    assert not re.search(r"\b(?:None|True|False)\b|\[\]", text)
    assert _examples(text, verb), text


def test_tf2_21_init_lists_every_flag_of_the_setup() -> None:
    shown = {flag for invocation, _ in help_entries(_help(["init"])) for flag in re.findall(r"--[a-z][a-z-]*", invocation)}
    assert set(INIT_FLAGS) <= shown, sorted(set(INIT_FLAGS) - shown)


def test_tf2_21_the_main_help_lists_both_verbs() -> None:
    text = _help([])
    listed = {m.group(1) for m in re.finditer(r"(?m)^ {2,}([a-z][\w-]*)(?: {2,}\S|$)", text)}
    assert {"init", "doctor"} <= listed, text


def _examples(text: str, verb: str) -> list[str]:
    """Every example of the verb's help, the bare command included."""
    joined = re.sub(r"\\\n\s*", " ", text)
    command = f"poisson-trace {verb}"
    return [s for s in (line.strip() for line in joined.splitlines()) if s == command or s.startswith(command + " ")]


def _option(words: list[str], flag: str) -> list[str]:
    return [words[i + 1] for i, w in enumerate(words[:-1]) if w == flag]


@pytest.mark.parametrize("verb", ["init", "doctor"])
def test_tf2_21_every_example_runs_as_written(tmp_path: Path, verb: str) -> None:
    found = _examples(_help([verb]), verb)
    assert found
    for i, example in enumerate(found):
        folder = work(tmp_path, f"example-{i}")
        words = shell_words(example)
        assert words[:2] == ["poisson-trace", verb], example
        stores = _option(words, "--store") + _option(words, "--add-store") or ["proofload-runs"]
        for store in dict.fromkeys(stores):
            tau2_copy(folder, store)
        if verb == "doctor" or "--add-store" in words:
            first = "proofload-runs" if "--add-store" in words else stores[0]
            if not (folder / first).exists():
                tau2_copy(folder, first)
            target = _option(words, "--config") or [CONFIG]
            write_config(folder, config_of(first), target[0])
        if verb == "init" and "--yes" not in words and "--add-store" not in words:
            result = tty(words[1:], ["", "", "", "", "", ""], cwd=folder)
        else:
            result = here(folder, words[1:])
        assert result.code == 0, (example, result.text)
        assert VERDICT_LINE.match(result.out.splitlines()[0]), (example, result.out[:200])
