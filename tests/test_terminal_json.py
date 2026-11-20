"""TF9, invariant 6: ``--json`` output is untouched (the look file's rule 16:
"``--json`` must be identical").

- **TF9-6a** Every verb's ``--json``, with stdout and stderr each on a terminal, prints the same
  bytes as on pipes, with the same exit code; no escape on either stream (on pipes it is the
  in-process document, TF9-1b).
- **TF9-6b** ``--json`` with ``--plain`` prints the same document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from terminal_support import JSON_ITEMS, Item, piped, shared_base, shared_run


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return shared_base(tmp_path_factory)


@pytest.mark.parametrize("item", JSON_ITEMS, ids=lambda i: i.label)
def test_tf9_6a_json_is_the_same_on_terminals(base: Path, item: Item) -> None:
    on_pipes = piped(base, item)
    on_terminals = shared_run(base, item, stdout="pty", stderr="own")
    assert on_pipes.code == item.expect
    assert (on_terminals.code, on_terminals.out) == (on_pipes.code, on_pipes.out)
    assert "\x1b" not in on_terminals.out and "\x1b" not in on_terminals.err


@pytest.mark.parametrize("item", JSON_ITEMS[:3], ids=lambda i: i.label)
def test_tf9_6b_json_with_plain_is_the_same_document(base: Path, item: Item) -> None:
    forced = Item(item.label + " --plain", item.command, (*item.argv, "--plain"), item.expect, item.stage)
    assert shared_run(base, forced, stdout="pty", stderr="own").out == piped(base, item).out
