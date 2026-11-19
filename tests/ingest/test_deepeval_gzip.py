"""ID13: a DeepEval file that is gzip and cannot be read is refused in one line, with no traceback
and no text of the library that failed.

Three ways a gzip file is damaged, each raising its own error in Python's gzip module: a
compressed stream that cannot be inflated (``zlib.error``), a checksum
that does not match (``gzip.BadGzipFile``) and a file cut short (``EOFError``). The damaged file
is the second of two, so that the refusal has to name it and the first file's rows are not
written. The reader knows gzip by a file's first two bytes, not by its name.
"""

from __future__ import annotations

import gzip
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest
from support import (
    IMPORT_MAIN, deepeval_argv, read_rows, refused, run_doc, run_import, run_python, save, scored, tree,
)


def _stream(raw: bytes) -> bytes:
    # the first byte of the deflate stream, after gzip's ten-byte header: a final block of the
    # reserved type 11
    return raw[:10] + b"\xff" + raw[11:]


def _checksum(raw: bytes) -> bytes:
    # the CRC-32 is the eight bytes before the end; its first byte flipped
    return raw[:-8] + bytes([raw[-8] ^ 0xFF]) + raw[-7:]


def _short(raw: bytes) -> bytes:
    return raw[: len(raw) // 2]


DAMAGE: dict[str, tuple[Callable[[bytes], bytes], type[BaseException]]] = {
    "stream": (_stream, zlib.error),
    "checksum": (_checksum, gzip.BadGzipFile),
    "short": (_short, EOFError),
}


def _files(tmp_path: Path, kind: str) -> tuple[Path, Path, str]:
    """A good file and a damaged one, and the text of the error Python's gzip module raises on
    the damaged one."""
    good = save(tmp_path / "test_run_20250905_185407.json", run_doc(scored("x", [0.9, 0.1])))
    damaged = save(tmp_path / "second.json.gz", run_doc(scored("x", [0.2, 0.8])), gz=True)
    damage, error = DAMAGE[kind]
    damaged.write_bytes(damage(damaged.read_bytes()))
    with pytest.raises(error) as raised:
        gzip.decompress(damaged.read_bytes())
    assert type(raised.value) is error
    return good, damaged, str(raised.value)


def _store(tmp_path: Path) -> Path:
    """A store already holding one run, which the refused import must leave as it is."""
    root = tmp_path / "store"
    first = save(tmp_path / "first.json", run_doc(scored("x", [0.3])))
    r = run_import(deepeval_argv(first, root, "v0", extra=("--started", "2025-09-05T00:00:00Z")))
    assert r.code == 0, r.text
    return root


@pytest.mark.parametrize("kind", list(DAMAGE))
def test_id13_a_damaged_gzip_file_is_refused_in_one_line_and_nothing_is_written(
    tmp_path: Path, kind: str
) -> None:
    good, damaged, _ = _files(tmp_path, kind)
    root = _store(tmp_path)
    before = tree(root)
    r = run_import(deepeval_argv([good, damaged], root, "v1"))
    refused(r)
    assert str(damaged) in r.err and str(good) not in r.err, r.err
    assert tree(root) == before


@pytest.mark.parametrize("kind", list(DAMAGE))
def test_id13_the_refusal_carries_no_traceback_and_no_text_of_the_library(
    tmp_path: Path, kind: str
) -> None:
    """Through the command as a process, so that anything that reaches stderr is seen, and with
    the files given by relative paths, as a user in that folder would give them."""
    good, damaged, library = _files(tmp_path, kind)
    root = tmp_path / "store"
    argv = deepeval_argv([Path(good.name), Path(damaged.name)], Path("store"), "v1")
    r = run_python(IMPORT_MAIN, argv, cwd=tmp_path)
    refused(r)
    assert damaged.name in r.err and str(damaged) not in r.err and good.name not in r.err, r.err
    assert "Traceback" not in r.err, r.err
    assert library not in r.err, r.err
    for name in ("zlib", "BadGzipFile", "EOFError"):
        assert name.lower() not in r.err.lower(), r.err
    assert not root.exists() or tree(root) == {}, tree(root)


def test_id13_gzip_is_known_by_its_first_bytes_not_by_its_name(tmp_path: Path) -> None:
    """Plain JSON named .json.gz and gzip named .json both import, to the rows of the same
    file saved as it is named."""
    doc = run_doc(scored("x", [0.9, 0.1, 0.6]))
    named = {
        "plain": save(tmp_path / "plain.json", doc),
        "plain named gz": save(tmp_path / "plain-named.json.gz", doc),
        "gzip named json": save(tmp_path / "gzip-named.json", doc, gz=True),
    }
    root = tmp_path / "store"
    rows = {}
    for i, (what, path) in enumerate(named.items()):
        r = run_import(deepeval_argv(path, root, f"v{i}", extra=("--started", "2025-09-05T00:00:00Z")))
        assert r.code == 0, (what, r.text)
        rows[what] = [(x["case"], x["outcome"]) for x in read_rows(root, f"v{i}")]
    assert rows["plain named gz"] == rows["plain"] == rows["gzip named json"], rows
