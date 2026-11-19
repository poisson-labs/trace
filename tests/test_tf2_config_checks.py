"""TF2-4: a config that is not a version 1 ``trace.toml`` is refused (spec section 3.2, rule L14;
yes/no 9).

Every way the file can be wrong is refused in one ``error:`` line that names the file as given and
the line the fault is written on, exit 1, before anything is read or written: a file TOML cannot
read; a table or a setting version 1 does not have, with the nearest one within two edits; a
value of the wrong type or out of its range, for every key of the table in section 3.2; a version
other than 1, naming this Trace's version; no version at all. Each case has a control: the same
file with that one clause put right is read, and the verb runs. Every verb that reads the config
refuses a wrong one, even when flags give the store and the events."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import poisson_trace
from tf0_support import deepeval_import
from tf1_support import tau2_copy
from tf2_support import config_of, here, import_here, scratch_home, work, write_config  # noqa: F401

S = "proofload-runs"
GOOD = config_of(S)


def _with(extra: str) -> str:
    return GOOD + extra


# (label, the wrong file, the line of the fault or None, the right file, the words the line holds)
CASES = [
    ("not TOML", 'version = 1\n\n[store\npath = "proofload-runs"\n', 3, GOOD, ()),
    ("a misspelt setting", GOOD.replace("version = 1", "versoin = 1"), 1, GOOD, ("version",)),
    ("a misspelt table", GOOD.replace("[events]", "[event]"), 6, GOOD, ("events",)),
    ("a misspelt key in a table", GOOD.replace("failed =", "faild ="), 7, GOOD, ("failed",)),
    ("version as text", GOOD.replace("version = 1", 'version = "1"'), 1, GOOD, ()),
    ("version as a decimal", GOOD.replace("version = 1", "version = 1.0"), 1, GOOD, ()),
    ("version as true", GOOD.replace("version = 1", "version = true"), 1, GOOD, ()),
    ("version 2", GOOD.replace("version = 1", "version = 2"), 1, GOOD, (poisson_trace.__version__,)),
    ("no version", GOOD.replace("version = 1\n", ""), None, GOOD, ()),
    ("a store path that is a number", GOOD.replace('path = "proofload-runs"', "path = 5"), 4, GOOD, ()),
    ("an empty store path", GOOD.replace('path = "proofload-runs"', 'path = ""'), 4, GOOD, ()),
    ("failures as text", GOOD.replace('failed = ["unsolved"]', 'failed = "unsolved"'), 7, GOOD, ()),
    ("no failures", GOOD.replace('failed = ["unsolved"]', "failed = []"), 7, GOOD, ()),
    ("a failure twice", GOOD.replace('failed = ["unsolved"]', 'failed = ["unsolved", "unsolved"]'), 7, GOOD, ()),
    ("an empty failure", GOOD.replace('failed = ["unsolved"]', 'failed = ["unsolved", ""]'), 7, GOOD, ()),
    ("a failure that is a number", GOOD.replace('failed = ["unsolved"]', 'failed = ["unsolved", 3]'), 7, GOOD, ()),
    ("max_mde at 0", _with("\n[check]\nmax_mde = 0\n"), 10, _with("\n[check]\nmax_mde = 0.2\n"), ()),
    ("max_mde at 1", _with("\n[check]\nmax_mde = 1\n"), 10, _with("\n[check]\nmax_mde = 0.999\n"), ()),
    ("max_mde as text", _with('\n[check]\nmax_mde = "0.2"\n'), 10, _with("\n[check]\nmax_mde = 0.2\n"), ()),
    ("max_mde as true", _with("\n[check]\nmax_mde = true\n"), 10, _with("\n[check]\nmax_mde = 0.2\n"), ()),
    ("max_mde_hr at 1", _with("\n[check]\nmax_mde_hr = 1\n"), 10, _with("\n[check]\nmax_mde_hr = 1.01\n"), ()),
    ("max_mde_hr below 1", _with("\n[check]\nmax_mde_hr = 0.5\n"), 10, _with("\n[check]\nmax_mde_hr = 1.5\n"), ()),
    ("a misspelt check", _with("\n[check]\nmax_md = 0.2\n"), 10, _with("\n[check]\nmax_mde = 0.2\n"), ("max_mde",)),
    ("fail_on not a list", _with('\n[check]\nfail_on = "failed-more"\n'), 10, _with('\n[check]\nfail_on = ["failed-more"]\n'), ()),
    ("fail_on not a result", _with('\n[check]\nfail_on = ["regressed"]\n'), 10, _with('\n[check]\nfail_on = ["too-small"]\n'), ()),
    ("fail_on twice", _with('\n[check]\nfail_on = ["too-small", "too-small"]\n'), 10, _with('\n[check]\nfail_on = ["too-small", "failed-more"]\n'), ()),
    ("names from a model", _with('\n[names]\nfrom = "model"\n'), 10, _with('\n[names]\nfrom = "target-date"\n'), ()),
    ("a store name with a space", _with('\n[store."my store"]\npath = "x"\n'), 9, _with('\n[store.my_store-2]\npath = "x"\n'), ()),
    ("a store name of 41 characters", _with(f'\n[store.{"s" * 41}]\npath = "x"\n'), 9, _with(f'\n[store.{"s" * 40}]\npath = "x"\n'), ()),
    ("a named store with no path", _with("\n[store.imported]\n"), None, _with('\n[store.imported]\npath = "x"\n'), ()),
    ("upload over plain http", _with('\n[upload]\nurl = "http://example.invalid/up"\n'), 10, _with('\n[upload]\nurl = "https://example.invalid/up"\n'), ()),
    ("upload to another scheme", _with('\n[upload]\nurl = "ftp://example.invalid/up"\n'), 10, _with('\n[upload]\nurl = "http://127.0.0.1:8080/up"\n'), ()),
    ("upload to a host named like loopback", _with('\n[upload]\nurl = "http://localhost.example.invalid/up"\n'), 10, _with('\n[upload]\nurl = "http://localhost/up"\n'), ()),
    ("upload to an address outside loopback", _with('\n[upload]\nurl = "http://128.0.0.1:8080/up"\n'), 10, _with('\n[upload]\nurl = "http://127.0.0.2:8080/up"\n'), ()),
    ("an upload token name with no token in it", _with('\n[upload]\ntoken_env = "SECRET"\n'), 10, _with('\n[upload]\ntoken_env = "MY_API_KEY"\n'), ()),
    ("upload switched by text", _with('\n[upload]\nenabled = "no"\n'), 10, _with('\n[upload]\nurl = "http://[::1]:9/up"\nenabled = false\n'), ()),
]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    place = work(tmp_path)
    tau2_copy(place, S)
    return place


@pytest.fixture(scope="module")
def shared_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One copy of the tau2 store for the tests that only read it: ``where`` writes nothing
    under a store."""
    return tau2_copy(tmp_path_factory.mktemp("tf2-config-checks"))


@pytest.fixture
def reading(tmp_path: Path, shared_store: Path) -> Path:
    """A folder of the test's own to write ``trace.toml`` in, holding the shared store under
    the name the config gives it (a link): for a test that reads the store and never writes it."""
    place = work(tmp_path)
    (place / S).symlink_to(shared_store, target_is_directory=True)
    return place


def _refused(result) -> str:  # type: ignore[no-untyped-def]
    assert result.code == 1 and result.out == "", result.text
    lines = result.lines()
    assert lines[0].startswith("error: ") and all(line.startswith("  next: ") for line in lines[1:]), result.err
    return lines[0]


@pytest.mark.parametrize("label,wrong,line,right,words", CASES, ids=[c[0] for c in CASES])
def test_tf2_04_a_wrong_config_is_refused_naming_the_file_and_the_line(reading: Path, label: str, wrong: str, line: int | None, right: str, words: tuple[str, ...]) -> None:
    folder = reading
    write_config(folder, wrong)
    error = _refused(here(folder, ["where", "previous", "--json"]))
    assert "trace.toml" in error, error
    if line is not None:
        assert re.search(rf"\bline {line}\b", error), error
    for word in words:
        assert word in error, error
    write_config(folder, right)
    control = here(folder, ["where", "previous", "--json"])
    assert control.code == 0, (label, control.text)


def test_tf2_04_the_nearest_setting_is_the_one_suggested(folder: Path) -> None:
    """``max_md`` is one edit from ``max_mde`` and four from ``max_mde_hr``."""
    write_config(folder, _with("\n[check]\nmax_md = 0.2\n"))
    error = _refused(here(folder, ["where", "previous"]))
    assert re.search(r"\bmax_mde\b(?!_)", error) and "max_mde_hr" not in error and "fail_on" not in error, error


def test_tf2_04_no_setting_is_singled_out_past_two_edits(folder: Path) -> None:
    """``zzzzzz`` is more than two edits from every setting of ``[check]``: none is offered as the
    one meant (a line may list them all, or none)."""
    write_config(folder, _with("\n[check]\nzzzzzz = 0.2\n"))
    error = _refused(here(folder, ["where", "previous"]))
    named = [k for k in (r"\bmax_mde\b(?!_)", r"\bmax_mde_hr\b", r"\bfail_on\b") if re.search(k, error)]
    assert len(named) != 1, error


def test_tf2_04_a_config_named_by_flag_is_named_as_given(folder: Path) -> None:
    (folder / "conf").mkdir()
    write_config(folder / "conf", GOOD.replace("failed =", "faild ="), "team.toml")
    error = _refused(here(folder, ["where", "previous", "--config", "conf/team.toml"]))
    assert "conf/team.toml" in error and re.search(r"\bline 7\b", error), error


@pytest.mark.parametrize("argv", [
    ["runs", "--store", S],
    ["name", "--list", "--store", S],
    ["where", "previous", "--store", S, "--event", "unsolved"],
    ["compare", "#3", "#2", "--store", S, "--event", "unsolved", "--max-mde-hr", "1.5"],
    ["fix-check", "#3", "#2", "--store", S, "--event", "unsolved", "--inputs", "all", "--max-mde", "0.2"],
    ["changes", "#3", "#2", "--store", S, "--event", "unsolved"],
], ids=["runs", "name", "where", "compare", "fix-check", "changes"])
def test_tf2_04_every_verb_refuses_a_wrong_config_even_given_every_flag(folder: Path, argv: list[str]) -> None:
    write_config(folder, GOOD.replace("[events]", "[events]\nlimit = 3"))
    _refused(here(folder, argv))
    write_config(folder, GOOD)
    assert here(folder, argv).code == 0


def test_tf2_04_a_wrong_config_writes_nothing(folder: Path) -> None:
    write_config(folder, GOOD.replace("version = 1", "version = 2"))
    _refused(here(folder, ["name", "previous", "old re-run"]))
    assert not (folder / S / "trace-names.toml").exists()


def test_tf2_04_the_import_refuses_a_wrong_config(tmp_path: Path) -> None:
    place = work(tmp_path)
    write_config(place, 'version = 1\n\n[store]\npath = "trace-store"\nlimit = 3\n')
    result = import_here(place, deepeval_import("trace-store", "he-a"))
    assert result.code == 1 and result.out == "", result.text
    assert not (place / "trace-store").exists()
