"""TF19-4: saves, and writes only through the core (``docs/app.md``, What it never does).

**TF19-4** Every verdict the app shows is saved, as ``api.save`` saves it, into the store the verb
saves into (B's store): the run screen's where, compare's, fix-check's and changes'. The message
line says ``saved  <kind> <first 12 hex>``, and the saved verdict is the one ``--save`` saves for
the same runs and settings (the same id; the same ``result.json`` but for the moment it was saved).
The pages are rebuilt with it. A store that cannot be written: the verdict is still shown and the
message line is ``note: the verdict was not saved: <the system's words>``. Nothing else is
written but through the core: a name only after its ``[y/N]`` is answered ``y`` (``api.name``),
an import only after its ``[y/N]`` is answered ``y`` (``api.import_run``); every other answer
writes nothing; browsing every screen writes nothing outside the stores' ``.poisson/``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from tf19_support import Type, app_world, changed, cli, copy_world, drive, found_steps, snapshot

SAVED = r"saved  {kind} {ident}"


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


@pytest.fixture
def work(world: Path, tmp_path: Path) -> Path:
    work = copy_world(world, tmp_path)
    # no verdict saved yet: every save the app makes is its own
    import shutil

    for store in ("store", "tables", "jstore"):
        shutil.rmtree(work / store / ".poisson" / "artifacts", ignore_errors=True)
        shutil.rmtree(work / store / ".poisson" / "ui", ignore_errors=True)
    return work


SHOWN = {
    "where": (["r", "enter"], ["where", "agent after"]),
    "compare": (["c", "enter"], ["compare", "agent before", "agent after"]),
    "fix-check": (["f", "enter"], ["fix-check", "agent before", "agent after", "--inputs", "all"]),
    "changes": (["f", "enter", "g"], ["changes", "agent before", "agent after"]),
}


def _artifacts(store: Path) -> set[tuple[str, str]]:
    base = store / ".poisson" / "artifacts"
    return {(p.parent.name, p.name) for p in base.glob("*/*") if p.is_dir()}


@pytest.mark.parametrize("kind", list(SHOWN))
def test_tf19_4_each_verdict_shown_is_saved(work: Path, tmp_path: Path, kind: str) -> None:
    keys, argv = SHOWN[kind]
    s = drive(work, keys, size=(120, 40))
    made = {(k, i) for k, i in _artifacts(work / "store") if k == kind}
    assert len(made) == 1, _artifacts(work / "store")
    (_, ident), = made
    assert s.last.message == SAVED.format(kind=kind, ident=ident[:12]), s.last.message
    assert any(name == "api.save" for name in s.spy.names())
    # the same verdict --save saves, by id and by result
    other = copy_world(work, tmp_path, "cli")
    import shutil

    shutil.rmtree(other / "store" / ".poisson" / "artifacts", ignore_errors=True)
    ran = cli(other, [*argv, "--save", "--json"])
    assert json.loads(ran.out)["saved"].endswith(f"/{kind}/{ident}")
    ours = json.loads((work / "store" / ".poisson" / "artifacts" / kind / ident / "result.json").read_text(encoding="utf-8"))
    theirs = json.loads((other / "store" / ".poisson" / "artifacts" / kind / ident / "result.json").read_text(encoding="utf-8"))
    assert ours == theirs
    # the pages hold it
    assert (work / "store" / ".poisson" / "ui" / "trace" / kind / f"{ident}.html").is_file()


def test_tf19_4_the_verdict_of_two_stores_is_saved_in_b_s(work: Path) -> None:
    """The table store's fix-check, the app on a config naming it: saved there."""
    (work / "imp").mkdir()
    (work / "imp" / "trace.toml").write_text('version = 1\n\n[store]\npath = "../tables"\n\n[events]\nfailed = ["missed"]\n\n[check]\nmax_mde = 0.5\n',
                                            encoding="utf-8")
    s = drive(work, ["f", "enter"], size=(120, 40), config="imp/trace.toml")
    made = _artifacts(work / "tables")
    assert {k for k, _ in made} == {"fix-check"}, made
    assert _artifacts(work / "store") == set()
    assert s.last.message.startswith("saved  fix-check ")


def test_tf19_4_a_store_that_cannot_be_written(work: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root writes through a read-only folder")
    store = work / "store"
    (store / ".poisson").mkdir(exist_ok=True)
    modes = {}
    for p in [store, *store.rglob("*")]:
        if p.is_dir():
            modes[p] = p.stat().st_mode
            p.chmod(0o555)
    try:
        before = snapshot(work)
        s = drive(work, ["c", "enter"], size=(120, 40))
    finally:
        for p, mode in modes.items():
            p.chmod(mode)
    g = s.last
    assert g.title() == "compare" and g.subject() == "agent before → agent after"
    assert g.message.startswith("note: the verdict was not saved: "), g.message
    assert len(g.message) > len("note: the verdict was not saved: ")
    assert changed(before, snapshot(work)) == set()
    assert s.code is None or s.code == 0


def test_tf19_4_browsing_writes_nothing_outside_the_stores_poisson(work: Path) -> None:
    before = snapshot(work)
    drive(work, ["r", "down", "up", "escape", "i", "escape", "c", "escape", "f", "escape", "?", "escape"], size=(120, 40))
    after = snapshot(work)
    moved = changed(before, after)
    assert all("/.poisson/" in f"/{m}" for m in moved), sorted(moved)
    assert not any("/.poisson/artifacts/" in f"/{m}" for m in moved), sorted(moved)


def test_tf19_4_showing_verdicts_writes_only_saves_and_pages(work: Path) -> None:
    before = snapshot(work)
    drive(work, ["c", "enter", "d", "escape", "escape", "f", "enter", "g"], size=(120, 40))
    moved = changed(before, snapshot(work))
    assert moved
    assert all(m.startswith("store/.poisson/artifacts/") or "/.poisson/ui/" in m for m in moved), sorted(moved)
    assert any(m.startswith("store/.poisson/artifacts/") for m in moved)


# ---------- a name ----------


def test_tf19_4_a_name_after_yes(work: Path) -> None:
    s = drive(work, ["r", "n", Type("tf19 name"), "enter", "<snap>", "y"], size=(120, 40))
    asked, done = s.grids[0], s.last
    assert asked.message.endswith("[y/N]") and "tf19 name" in asked.message, asked.message
    calls = s.spy.called("api.name")
    assert len(calls) == 1 and "tf19 name" in calls[0][0], calls
    result = s.spy.results("api.name")[0]
    assert done.message == f"{result.verdict}  {result.sentence}"
    listed = json.loads(cli(work, ["runs", "--json"]).out)["runs"]
    assert listed[0]["name"] == "tf19 name"
    assert any("tf19 name" in r for r in done.body)


@pytest.mark.parametrize("answer", ["n", "escape", "enter", "q", "x"])
def test_tf19_4_a_name_after_no_writes_nothing(work: Path, answer: str) -> None:
    before = snapshot(work)
    steps = ["r", "n", Type("never"), "enter", answer]
    if answer == "x":
        steps.append("n")
    s = drive(work, steps, size=(120, 40))
    assert s.spy.called("api.name") == []
    moved = changed(before, snapshot(work))
    assert not any(".poisson/artifacts" in m or "names" in m.split("/")[-1] for m in moved), moved
    assert s.code is None, "q during a question answers no and does not quit"
    assert s.last.title() == "runs"
    if answer == "q":
        assert not s.last.message.endswith("[y/N]"), "the question is gone from the message line"


# ---------- an import ----------


def _first_runnable(work: Path) -> tuple[int, object]:
    from poisson_trace import core

    found = [f for f in core.found_results(work, store="jstore") if not f.imported]
    for i, f in enumerate(found):
        if not f.fill:
            return i, f
    raise AssertionError("no found file to import")


def test_tf19_4_an_import_after_yes(work: Path) -> None:
    i, f = _first_runnable(work)
    before = set(p.name for p in (work / "jstore").iterdir())
    s = drive(work, [*found_steps(work, i), "<snap>", "y"], size=(120, 40))
    asked, done = s.grids[0], s.last
    assert asked.message.endswith("[y/N]"), asked.message
    calls = s.spy.called("api.import_run")
    assert len(calls) == 1, calls
    result = s.spy.results("api.import_run")[0]
    assert done.message == f"{result.verdict}  {result.sentence}", done.message
    after = set(p.name for p in (work / "jstore").iterdir())
    assert len(after - before) == 1, after - before
    assert done.title() == "imports"
    assert not any(r[2:].startswith(f"{f.path} ") for r in done.body), f.path  # imported now: no longer listed


@pytest.mark.parametrize("answer", ["n", "escape", "enter", "q"])
def test_tf19_4_an_import_after_no_writes_nothing(work: Path, answer: str) -> None:
    i, _f = _first_runnable(work)
    before = snapshot(work)
    s = drive(work, [*found_steps(work, i), answer], size=(120, 40))
    assert s.spy.called("api.import_run") == []
    moved = changed(before, snapshot(work))
    assert all("/.poisson/ui/" in f"/{m}" for m in moved), moved
    assert s.code is None
    assert s.last.title() == "imports"


def test_tf19_4_a_line_with_a_word_to_fill_is_never_run(work: Path) -> None:
    from poisson_trace import core

    found = [f for f in core.found_results(work, store="jstore") if not f.imported]
    i = next(k for k, f in enumerate(found) if f.fill)
    before = snapshot(work)
    s = drive(work, [*found_steps(work, i), "<snap>", "y"], size=(120, 40))
    shown = s.grids[0]
    assert shown.message.startswith("note: ") and all(w in shown.message for w in found[i].fill), shown.message
    assert not shown.message.endswith("[y/N]")
    assert found[i].command.replace(" ", "") in "".join(shown.body).replace(" ", "")
    assert s.spy.called("api.import_run") == []
    assert all("/.poisson/ui/" in f"/{m}" for m in changed(before, snapshot(work)))
