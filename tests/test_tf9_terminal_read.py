"""TF9: how the other clean-look tests read a pseudo-terminal back.

- **TF9-T1** What a command writes to a terminal is read back as it wrote it. On macOS, when the
  ``\\r`` the terminal adds before a line feed takes the last slot of its 1024-character output
  queue, the kernel retries the line feed and writes ``\\r`` a second time. So a long enough output
  comes back with ``\\r\\r\\n``. That is the terminal's, not the command's, and it is read as
  ``\\n``; a ``\\r`` that is not before a line feed is the command's redraw, and stays (TF9-4d reads
  it).
"""

from __future__ import annotations

from pathlib import Path

from tf9_support import run

#: Short lines, so that many line feeds land on the queue's last slot; a redraw first.
WRITTEN = "a\rb\n" + "x\n" * 15000


def test_tf9_t1_a_terminal_is_read_back_as_it_was_written(tmp_path: Path) -> None:
    prelude = f"import os, sys\nsys.stdout.write({WRITTEN!r})\nsys.stdout.flush()\nos._exit(0)\n"
    r = run([], cwd=tmp_path, home=tmp_path, prelude=prelude)
    assert r.code == 0
    assert r.out == WRITTEN
