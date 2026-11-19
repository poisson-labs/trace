"""TF9, invariant 1: plain stays the contract (the look file's rule 16).

- Every frozen test is unchanged, byte for byte: the plain output those tests pin is pinned
  still, and the clean look moves none of them.
  ``test_frozen.py`` holds it, with the one list of every frozen file.
- **TF9-1b** Piped, the build with the pretty rendering prints the plain rendering byte for byte:
  every invocation of the conformance corpus (``tf0_support.corpus``), run in a process of its
  own on two pipes under an environment where every other condition of the switch holds, prints
  what the same invocation prints in-process, stdout and stderr, with the same exit code.
- **TF9-1c** ``--plain`` given to a command that is not on a terminal changes nothing.

The whole suite passing is the rest of this invariant: those tests run in-process on captured
streams, which are not terminals, so they read the plain rendering.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tf0_support import Item, chdir, corpus, prepare, run_item, trace, trace_import
from tf9_support import child_env

# ---------- TF9-1b: piped, pretty is plain ----------

CORPUS = corpus()
#: The corpus's imports write the store ``imported``, and its fix check on the imports reads it.
_WRITES = {"import deepeval", "import deepeval, the other version", "import ragas as JSON"}


@pytest.fixture(scope="module")
def folders(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Two starting folders: as ``prepare`` leaves it, and with the corpus's imports made."""
    bare = prepare(tmp_path_factory.mktemp("tf9-bare") / "w")
    full = tmp_path_factory.mktemp("tf9-full") / "w"
    shutil.copytree(bare, full)
    with chdir(full):
        for item in CORPUS:
            if item.label in _WRITES:
                assert run_item(item).code == 0
    return {"bare": bare, "full": full}


def _sub(item: Item, cwd: Path, home: Path) -> tuple[int, str, str]:
    import subprocess
    import sys

    from tf0_support import script

    proc = subprocess.run(
        [sys.executable, "-c", script(item.command), *item.argv], cwd=cwd, env=child_env(home),
        stdin=subprocess.DEVNULL, capture_output=True, timeout=300,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("item", CORPUS, ids=lambda i: i.label)
def test_tf9_1b_piped_the_pretty_build_prints_plain_byte_for_byte(item: Item, folders: dict[str, Path], tmp_path: Path) -> None:
    start = folders["bare" if item.label in _WRITES else "full"]
    work, home = tmp_path / "w", tmp_path / "home"
    home.mkdir()
    shutil.copytree(start, work)
    with chdir(work):
        inside = run_item(item)
    shutil.rmtree(work)
    shutil.copytree(start, work)  # the same path, so a path in the output reads the same
    code, out, err = _sub(item, work, home)
    assert (code, out, err) == (inside.code, inside.out, inside.err)


# ---------- TF9-1c: --plain off a terminal ----------


@pytest.mark.parametrize(
    "label", ["where", "compare, too small to tell", "changes", "a store that is not there", "an unknown option"]
)
@pytest.mark.parametrize("place", ["after the verb", "before the verb"])
def test_tf9_1c_plain_off_a_terminal_changes_nothing(label: str, place: str) -> None:
    item = next(i for i in CORPUS if i.label == label)
    given = [*item.argv, "--plain"] if place == "after the verb" else ["--plain", *item.argv]
    assert trace(given) == trace(item.argv)


@pytest.mark.parametrize("place", ["after the tool", "before the tool"])
def test_tf9_1c_plain_off_a_terminal_changes_nothing_for_the_import(place: str, tmp_path: Path) -> None:
    from tf0_support import deepeval_import

    argv = deepeval_import("store", "he-a")
    given = [*argv, "--plain"] if place == "after the tool" else ["--plain", *argv]
    work = tmp_path / "w"
    work.mkdir()
    with chdir(work):
        bare = trace_import(argv)
    shutil.rmtree(work)
    work.mkdir()  # the same path, so a path in the output reads the same
    with chdir(work):
        forced = trace_import(given)
    assert bare.code == 0
    assert forced == bare
