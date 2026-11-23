"""``doctor`` fails its config check when a store the config names has a broken ``store.json``.

Every command that opens such a store refuses it, in one line naming the file:

    error: store/.poisson/store.json is not a store descriptor (not a JSON object); nothing was written

``doctor`` read the config's stores without opening their descriptor, and said the environment
was ready while every verb refused. It now fails its config check (exit 4), as it does for a store
in a newer format, with the line ``CONFIG: SENTENCE``: the config as doctor names it, and the
sentence the verbs print after ``error:``. Its Prove check stays ok. ``doctor --setup`` fails the
same check, with the exit code it gives for a store in a newer format. A store with no
``store.json`` is still ready.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from prove_floor_support import EVENT, STORE_1_2, copy, descriptor_file, run, tree

BROKEN = {"cut short": None, "a list": "[]\n", "not text": b"\xff\xfe\x00{"}


def _set_up(tmp_path: Path) -> Path:
    store = copy(STORE_1_2, tmp_path)
    assert run(["init", "--store", "store", *EVENT, "--yes"], tmp_path).code == 0
    assert run(["doctor"], tmp_path).code == 0
    return store


def _break(store: Path, how: str) -> None:
    text = BROKEN[how]
    file = descriptor_file(store)
    if text is None:
        file.write_text(file.read_text(encoding="utf-8")[:40], encoding="utf-8")
    elif isinstance(text, bytes):
        file.write_bytes(text)
    else:
        file.write_text(text, encoding="utf-8")


def _verbs_say(tmp_path: Path) -> str:
    """The sentence a verb reading the config's store prints after ``error:``."""
    ran = run(["runs"], tmp_path)
    assert ran.code == 1 and ran.lines()[0].startswith("error: "), ran.text
    return ran.lines()[0][len("error: "):]


def _config_check(ran_json: dict[str, object]) -> dict[str, object]:
    checks = ran_json["checks"]
    assert isinstance(checks, list)
    (config,) = [c for c in checks if c["name"] == "config"]
    (prove,) = [c for c in checks if c["name"] == "prove"]
    assert prove["ok"] is True, prove
    return dict(config)


@pytest.mark.parametrize("how", list(BROKEN))
def test_doctor_fails_its_config_check_with_the_verbs_sentence(tmp_path: Path, how: str) -> None:
    store = _set_up(tmp_path)
    _break(store, how)
    said = _verbs_say(tmp_path)
    assert "store.json is not a store descriptor" in said, said
    before = tree(tmp_path)
    ran = run(["doctor", "--json"], tmp_path)
    assert ran.code == 4, ran.text
    config = _config_check(ran.json())
    assert config["ok"] is False and config["line"] == f"trace.toml: {said}", config
    plain = run(["doctor"], tmp_path)
    assert plain.code == 4, plain.text
    assert plain.out.splitlines()[0].startswith("not ready  config fails"), plain.out
    assert f"trace.toml: {said}" in plain.out and "Traceback" not in plain.text, plain.text
    assert tree(tmp_path) == before, "doctor writes nothing"


def test_doctor_setup_fails_the_same_check_as_for_a_newer_store(tmp_path: Path) -> None:
    store = _set_up(tmp_path)
    descriptor = descriptor_file(store).read_text(encoding="utf-8")
    doc = json.loads(descriptor)
    doc["format"] = "poisson.store/2"
    descriptor_file(store).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    newer = run(["doctor", "--setup", "--json"], tmp_path)
    assert newer.code != 0, newer.text
    _break(store, "a list")
    said = _verbs_say(tmp_path)
    ran = run(["doctor", "--setup", "--json"], tmp_path)
    assert ran.code == newer.code, ran.text
    config = _config_check(ran.json())
    assert config["ok"] is False and config["line"] == f"trace.toml: {said}", config


def test_a_config_named_by_flag_is_named_as_doctor_names_it(tmp_path: Path) -> None:
    store = _set_up(tmp_path)
    _break(store, "cut short")
    sub = tmp_path / "sub"
    sub.mkdir()
    ran = run(["runs", "--config", "../trace.toml"], sub)
    said = ran.lines()[0][len("error: "):]
    assert said.startswith("../store/.poisson/store.json"), said
    checked = run(["doctor", "--config", "../trace.toml", "--json"], sub)
    assert checked.code == 4, checked.text
    assert _config_check(checked.json())["line"] == f"../trace.toml: {said}"


def test_a_store_with_no_store_json_is_still_ready(tmp_path: Path) -> None:
    store = _set_up(tmp_path)
    descriptor_file(store).unlink()
    assert run(["doctor"], tmp_path).code == 0
