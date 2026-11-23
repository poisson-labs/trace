"""A store whose ``.poisson/store.json`` is broken is refused by every command that opens the store,
as ``--save`` already refuses it.

Broken means the file is there and is not a store descriptor: not text, not JSON, or JSON that
is not an object. It is not a newer format, which is refused in its own words. ``--save`` and
``api.save`` refuse such a store in one line naming the file:

    error: STORE/.poisson/store.json is not a store descriptor (JSONDecodeError); nothing was written

with what is wrong in the brackets. Every command that reads the store (``runs``, ``name --list``,
``where``, ``compare``, ``fix-check``, ``changes``, with or without ``--json``), ``ui``, ``name``
and ``init`` now refuse it with that same line: exit 1, nothing on stdout, no ``next:`` line, and
nothing written. Through the API, ``open_store`` and the reading functions refuse it with the
message ``api.save`` gives. A store with no ``store.json`` still reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from prove_floor_support import (
    EVENT, READING, SAVING, STORE_1_2, WRITING, argv_of, copy, descriptor_file, python, refused_one_line, run, tree,
    with_descriptor,
)

BROKEN: dict[str, str | bytes | None] = {
    "cut short": None,
    "not json": "{not json\n",
    "empty": "",
    "not text": b"\xff\xfe\x00{",
    "a list": "[]\n",
    "a string": '"poisson.store/1"\n',
    "null": "null\n",
}
FAULT = {"cut short": "JSONDecodeError", "not json": "JSONDecodeError", "empty": "JSONDecodeError",
         "not text": "UnicodeDecodeError", "a list": "not a JSON object", "a string": "not a JSON object",
         "null": "not a JSON object"}


def _broken(tmp_path: Path, how: str) -> Path:
    text = BROKEN[how]
    if text is None:
        text = descriptor_file(STORE_1_2).read_text(encoding="utf-8")[:40]
    if isinstance(text, bytes):
        root = copy(STORE_1_2, tmp_path)
        descriptor_file(root).write_bytes(text)
        return root
    return with_descriptor(STORE_1_2, tmp_path, text)


def _line(store: Path, how: str) -> str:
    return f"error: {descriptor_file(store)} is not a store descriptor ({FAULT[how]}); nothing was written"


def _refused(tmp_path: Path, store: Path, argv: list[str], how: str) -> None:
    before = tree(tmp_path)
    ran = run(argv, tmp_path)
    line = refused_one_line(ran, "store.json")
    assert ran.lines() == [line] == [_line(store, how)], ran.err
    assert tree(tmp_path) == before, "a refusal writes nothing"


@pytest.mark.parametrize("how", list(BROKEN))
def test_save_refuses_with_the_line_every_other_command_now_gives(tmp_path: Path, how: str) -> None:
    store = _broken(tmp_path, how)
    _refused(tmp_path, store, argv_of(SAVING["fix-check --save"], store, STORE_1_2), how)


@pytest.mark.parametrize("label", list(READING))
def test_every_reading_command_refuses_a_broken_store_json(tmp_path: Path, label: str) -> None:
    store = _broken(tmp_path, "cut short")
    _refused(tmp_path, store, argv_of(READING[label], store, STORE_1_2), "cut short")


@pytest.mark.parametrize("how", list(BROKEN))
def test_whatever_is_wrong_with_the_file(tmp_path: Path, how: str) -> None:
    store = _broken(tmp_path, how)
    for label in ("runs", "where --json"):
        _refused(tmp_path, store, argv_of(READING[label], store, STORE_1_2), how)


@pytest.mark.parametrize("how", ["cut short", "a list"])
@pytest.mark.parametrize("label", ["name", "ui"])
def test_ui_and_name_refuse_it_and_write_nothing(tmp_path: Path, label: str, how: str) -> None:
    store = _broken(tmp_path, how)
    _refused(tmp_path, store, argv_of(WRITING[label], store, STORE_1_2), how)
    assert not (store / ".poisson" / "ui").exists() and not (store / "trace-names.toml").exists()


@pytest.mark.parametrize("how", ["cut short", "a list"])
def test_init_refuses_to_set_it_up_and_writes_no_config(tmp_path: Path, how: str) -> None:
    store = _broken(tmp_path, how)
    _refused(tmp_path, store, ["init", "--store", str(store), *EVENT, "--yes"], how)
    assert not (tmp_path / "trace.toml").exists()


def test_init_refuses_it_when_it_finds_the_store_itself(tmp_path: Path) -> None:
    store = _broken(tmp_path, "cut short")
    before = tree(tmp_path)
    ran = run(["init", *EVENT, "--yes"], tmp_path)
    assert ran.code == 1, ran.text
    assert _line(Path("store"), "cut short") in ran.err or _line(store, "cut short") in ran.err, ran.err
    assert "unexpected failure" not in ran.err and "Traceback" not in ran.err, ran.err
    assert tree(tmp_path) == before
    assert not (tmp_path / "trace.toml").exists()


_API = """\
import sys
from poisson_trace import api
store = sys.argv[1]
saved = None
try:
    api.save(api.where(store, "agent after", event=["violated"]))
except api.Refusal as e:
    saved = e
print("save", saved.exit_code if saved else None, saved.message if saved else None, list(saved.next) if saved else None)
for name, call in (("open_store", lambda: api.open_store(store)), ("runs", lambda: api.runs(store)),
                   ("where", lambda: api.where(store, "agent after", event=["violated"]))):
    try:
        call()
        print(name, "read")
    except api.Refusal as e:
        print(name, e.exit_code, e.message, list(e.next))
"""


def test_the_api_refuses_it_with_the_message_save_gives(tmp_path: Path) -> None:
    store = _broken(tmp_path, "cut short")
    ran = python(_API, [store], tmp_path)
    assert ran.code == 0, ran.text
    message = _line(store, "cut short")[len("error: "):]
    lines = ran.out.splitlines()
    assert lines[0] == f"save 1 {message} []", lines
    assert lines[1:] == [f"{name} 1 {message} []" for name in ("open_store", "runs", "where")], lines


def test_a_store_with_no_store_json_still_reads(tmp_path: Path) -> None:
    store = copy(STORE_1_2, tmp_path)
    descriptor_file(store).unlink()
    for label in ("runs", "where --json"):
        assert run(argv_of(READING[label], store, STORE_1_2), tmp_path).code == 0
