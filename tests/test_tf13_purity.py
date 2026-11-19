"""TF13-24 to TF13-27: what the API never does.

TF13-24: it prints nothing, on either stream; what the command line prints as ``note:`` lines
the API hands back as ``notes``.

TF13-25: it reads no environment variable: none is read by the package's own code while a
function runs, and the variables that change the command line's look change nothing it returns.

TF13-26: it reads no file and lists no folder it was not given a path to: every file opened and
folder listed is under a path the call was given, or where Python and the installed packages
live; a ``trace.toml`` and a names file in the current folder change nothing.

TF13-27: it writes only in ``to_bundle``, ``save``, ``import_run``, ``name``, ``forget_name``
and ``write_svg``, and each writes only where it was pointed; a folder it makes for its own work
is under the system's temporary folder and gone when it returns.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from tf13_support import (
    IMPORT_ARGV, VERBS_ARGV, api, attempt, call_for, cli, import_call_for, notes_of, outside,
    Outcome, Watch, python_roots, snapshot, watched, workspace,
)

READING = ["where", "where untraced", "compare", "fix-check measures", "fix-check verdicts", "changes verdicts",
           "runs", "runs no event", "where config", "fix-check config", "changes config name",
           "where with a run Prove cannot read", "fix-check with a run Prove cannot read"]


def _given(work: Path, label: str) -> list[Path]:
    """The paths an invocation names: its store (and the config's stores), its config, its
    verdicts file."""
    argv = VERBS_ARGV[label]
    out = []
    for flag in ("--store", "--config", "--verdicts"):
        if flag in argv:
            out.append(work / argv[argv.index(flag) + 1])
    if "--config" in argv:
        out += [work / "store", work / "tables"]
    return out


def _reads(work: Path) -> dict[str, Any]:
    a = api()
    return {
        "open_store": (lambda: a.open_store("store"), [work / "store"]),
        "load_config": (lambda: a.load_config("conf/trace.toml"), [work / "conf" / "trace.toml"]),
        "list_names": (lambda: a.list_names("store"), [work / "store"]),
        "to_json and to_markdown": (lambda: (lambda r: (r.to_json(), r.to_markdown(), r.to_svg()))(
            a.where("store", "agent after", event=["violated", "timeout"])), [work / "store"]),
    }


@dataclass(frozen=True)
class Watched:
    """One reading call made once, watched, in a workspace of its own: what it gave, what the
    watch saw, the workspace before and after, and what was left in the temporary folder."""

    work: Path
    got: Outcome
    watch: Watch
    before: dict[str, str]
    after: dict[str, str]
    left: list[Path]


@pytest.fixture(scope="module")
def watched_call(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Watched]:
    """Each label's call, its result and both its texts read, made once for the three tests that
    read what the watch saw (TF13-25, TF13-26, TF13-27); none of them writes to what it is given."""
    made: dict[str, Watched] = {}

    def of(label: str) -> Watched:
        if label not in made:
            root = tmp_path_factory.mktemp("watched")
            work = workspace(root)
            before = snapshot(work)
            call = call_for(VERBS_ARGV[label])
            temp = root / "systemp"
            with watched(temp) as watch:
                got = attempt(lambda: (lambda r: (r, r.to_json(), r.to_markdown()))(call()), work)
            made[label] = Watched(work, got, watch, before, snapshot(work), list(temp.iterdir()))
        return made[label]

    return of


# ---------- TF13-24 ----------


@pytest.mark.parametrize("label", READING)
def test_tf13_24_the_api_prints_nothing(tmp_path: Path, label: str, capfd: pytest.CaptureFixture[str]) -> None:
    work = workspace(tmp_path)
    ran = cli(work, VERBS_ARGV[label])
    capfd.readouterr()
    got = attempt(call_for(VERBS_ARGV[label]), work)
    seen = capfd.readouterr()
    assert got.out == got.err == "" and seen.out == seen.err == "", label
    assert tuple(got.result.notes) == notes_of(ran.err), label


# ---------- TF13-25 ----------


@pytest.mark.parametrize("label", READING)
def test_tf13_25_the_api_reads_no_environment_variable(watched_call: Callable[[str], Watched], label: str) -> None:
    ran = watched_call(label)
    assert ran.got.refusal is None
    assert ran.watch.env == [], ran.watch.env


def test_tf13_25_a_the_look_s_variables_change_nothing_the_api_returns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = workspace(tmp_path)
    call = call_for(VERBS_ARGV["fix-check measures"])
    plain = attempt(call, work).result
    for name, value in {"NO_COLOR": "1", "CI": "true", "COLUMNS": "40", "TERM": "dumb", "LANG": "C",
                        "PYTHONIOENCODING": "ascii", "POISSON_TRACE_UPLOAD_URL": "https://example.invalid/x"}.items():
        monkeypatch.setenv(name, value)
    again = attempt(call, work).result
    assert (again.to_json(), again.to_markdown()) == (plain.to_json(), plain.to_markdown())


def test_tf13_25_b_the_import_and_the_writers_read_no_environment_variable(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    a = api()
    with watched(tmp_path / "systemp") as watch:
        attempt(import_call_for(IMPORT_ARGV["junit"]), work)
        attempt(lambda: a.name("store", "agent after", "shipped"), work)
        attempt(lambda: a.forget_name("store", "shipped"), work)
        attempt(lambda: a.save(call_for(VERBS_ARGV["fix-check"])()).to_bundle("bundle"), work)
        attempt(lambda: a.validate_bundle("bundle"), work)
        attempt(lambda: a.load_bundle("bundle"), work)
    assert watch.env == [], watch.env


# ---------- TF13-26 ----------


@pytest.mark.parametrize("label", READING)
def test_tf13_26_the_api_reads_nothing_it_was_not_given(watched_call: Callable[[str], Watched], label: str) -> None:
    ran = watched_call(label)
    watch = ran.watch
    assert ran.got.refusal is None
    allowed = [*_given(ran.work, label), *python_roots()]
    assert outside(watch.opened, allowed) == [], outside(watch.opened, allowed)
    assert outside(watch.listed, allowed) == [], outside(watch.listed, allowed)


def test_tf13_26_a_the_other_functions_read_nothing_they_were_not_given(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    assert cli(work, [*VERBS_ARGV["fix-check"], "--out", "bundle"]).code == 0
    a = api()
    reads = {**_reads(work), "load_bundle": (lambda: a.load_bundle("bundle"), [work / "bundle"]),
             "validate_bundle": (lambda: a.validate_bundle("bundle"), [work / "bundle"])}
    for label, (fn, given) in reads.items():
        with watched(tmp_path / "systemp") as watch:
            got = attempt(fn, work)
        assert got.refusal is None, label
        allowed = [*given, *python_roots()]
        assert outside(watch.opened, allowed) == [] and outside(watch.listed, allowed) == [], (label, watch.opened, watch.listed)


def test_tf13_26_b_a_config_and_names_in_the_current_folder_change_nothing(tmp_path: Path) -> None:
    """The command line reads the current folder's ``trace.toml``; the API reads a config only
    when given its path."""
    work = workspace(tmp_path)
    a = api()
    bare = attempt(lambda: a.where("store", "agent after", event=["violated"]), work)
    (work / "trace.toml").write_text('version = 1\n[store]\npath = "tables"\n[events]\nfailed = ["missed"]\n',
                                     encoding="utf-8")
    (work / "trace-names.toml").write_text('[runs]\n"20261104T162928Z-1596" = "a name from the wrong place"\n', encoding="utf-8")
    again = attempt(lambda: a.where("store", "agent after", event=["violated"]), work)
    assert again.refusal is None and again.result.to_markdown() == bare.result.to_markdown()
    assert again.result.to_json() == bare.result.to_json()
    # with no store given and no config given, the API does not go looking for one
    nothing = attempt(lambda: a.where(None, "agent after", event=["violated"]), work)
    assert nothing.refusal is not None and nothing.refusal.exit_code == 2
    assert "--store is required" in nothing.refusal.message


# ---------- TF13-27 ----------


@pytest.mark.parametrize("label", READING)
def test_tf13_27_the_reading_functions_write_nothing(watched_call: Callable[[str], Watched], label: str) -> None:
    ran = watched_call(label)
    assert ran.got.refusal is None
    assert ran.watch.written == [], ran.watch.written
    assert ran.after == ran.before
    assert ran.left == []


def test_tf13_27_a_each_writer_writes_only_where_it_was_pointed(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    a = api()
    temp = tmp_path / "systemp"
    unsaved = attempt(call_for(VERBS_ARGV["where"]), work).result
    writers = {
        "save": (lambda: a.save(unsaved), [work / "store"]),
        "to_bundle": (lambda: unsaved.to_bundle("bundle"), [work / "store", work / "bundle"]),
        "write_svg": (lambda: unsaved.write_svg("curve.svg"), [work / "curve.svg"]),
        "name": (lambda: a.name("store", "agent after", "shipped"), [work / "store"]),
        "forget_name": (lambda: a.forget_name("store", "shipped"), [work / "store"]),
        "import_run": (import_call_for(IMPORT_ARGV["junit"]), [work / "new-store"]),
        "import_run with verdicts": (import_call_for(IMPORT_ARGV["table verdicts"]), [work / "new-store"]),
    }
    for label, (fn, targets) in writers.items():
        before = snapshot(work)
        with watched(temp) as watch:
            got = attempt(fn, work)
        assert got.refusal is None, (label, got.refusal)
        assert watch.written, (label, "it wrote")
        assert outside(watch.written, [*targets, temp]) == [], (label, outside(watch.written, [*targets, temp]))
        after = snapshot(work)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        rel = [t.relative_to(work).as_posix() for t in targets]
        assert all(any(k == r or k.startswith(r + "/") for r in rel) for k in changed), (label, sorted(changed))
        assert list(temp.iterdir()) == [], (label, "a folder of its own work left behind")


def test_tf13_27_b_runs_read_from_folders_leave_nothing_behind(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    (work / "folders" / "ja").mkdir(parents=True)
    (work / "folders" / "jb").mkdir()
    (work / "folders" / "ja" / "a.xml").write_bytes((work / "files" / "humaneval-a.xml").read_bytes())
    (work / "folders" / "jb" / "b.xml").write_bytes((work / "files" / "humaneval-b.xml").read_bytes())
    before = snapshot(work)
    temp = tmp_path / "systemp"
    with watched(temp) as watch:
        got = attempt(lambda: api().fix_check(None, "folders/ja", "folders/jb", event=["missed"], inputs="all", max_mde=0.1), work)
    assert got.refusal is None
    assert outside(watch.written, [temp]) == [], watch.written
    assert snapshot(work) == before and list(temp.iterdir()) == []
