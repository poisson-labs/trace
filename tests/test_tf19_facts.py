"""TF19-3: the facts rule: each screen carries what its plain command prints.

**TF19-3** Each screen carries every fact its plain command prints for the same runs and settings
(the command run in the same folder, so with the same ``trace.toml``): every number as the command
prints it, every run id, every saved id at 12 hex, every command it names. What a screen's keys
show (``m`` the lines with no room, ``k`` the failures by kind, ``t`` the second table) and its
could not say screen (``d``) count as the screen's; the screens are read at 120 columns and tall
enough to show their tables whole. (The verdict line being the command's, word and sentence, is
held with each screen's frame, TF19-2.) The summary's lines and every line of "Before you act on this" are on the verdict screen whole, never
shortened, at 120 × 40 and at 80 × 24; at 80 × 24 the lines with no room are behind one key,
``m``, the screen says how many, and the links block stays on screen. Could not say carries
each sentence of the report's "What this cannot say" whole; for a verdict on an imported store,
the sentence a run with no traces adds ("This run has no traces ...") too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tf19_support import (
    Grid,
    app_world,
    cli,
    copy_world,
    drive,
    missing_facts,
    name_shown,
    norm,
    section_lines,
    summary_values,
)


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return app_world(tmp_path_factory)


@pytest.fixture
def work(world: Path, tmp_path: Path) -> Path:
    return copy_world(world, tmp_path)


TALL = (120, 200)

#: Each screen: how it is reached, the keys that show what it keeps behind one, and its command.
SCREENS: dict[str, tuple[list[str], list[str], list[str]]] = {
    "run": (["r", "enter"], ["m", "t"], ["where", "agent after"]),
    "verdict compare": (["c", "enter"], ["m", "k"], ["compare", "agent before", "agent after"]),
    "verdict fix-check": (["f", "enter"], ["m", "k", "t"], ["fix-check", "agent before", "agent after", "--inputs", "all"]),
    "changes": (["f", "enter", "g"], ["m", "k"], ["changes", "agent before", "agent after"]),
    "runs": (["r"], [], ["runs"]),
}


#: How far the lines behind ``m`` are read: a page down at a time.
PAGES_DOWN = 6


def _behind_m(work: Path, reach: list[str], size: tuple[int, int]) -> list[Grid]:
    """The screen, and when it says lines are behind ``m``, those lines a page at a time: ``m``,
    then ``pagedown`` until they end. Every line is whole on one of the reads."""
    s = drive(work, [*reach, "<snap>", "m", "<snap>", *[x for _ in range(PAGES_DOWN) for x in ("pagedown", "<snap>")]], size=size)
    first = s.grids[0]
    if not any("more lines above the table: m shows them" in r for r in first.body):
        return [first]
    return s.grids


def _read(work: Path, reach: list[str], behind: list[str], size: tuple[int, int] = TALL, with_d: bool = True) -> str:
    """The screen's body text, each view behind its keys (a key pressed again goes back),
    and its could not say screen, read in one session."""
    steps: list[object] = [*reach, "<snap>"]
    for key in behind:
        steps += [key, "<snap>", key]
    if with_d:
        steps += ["d", "<snap>"]
    s = drive(work, steps, size=size)
    texts = [g.body_text() for g in s.grids if g.title() != "could not say" or with_d]
    if with_d:
        assert s.grids[-1].title() == "could not say", s.grids[-1].text()
    return " ".join(texts)


@pytest.mark.parametrize("screen", list(SCREENS))
def test_tf19_3_every_fact_of_the_plain_command(work: Path, screen: str) -> None:
    reach, behind, argv = SCREENS[screen]
    shown = _read(work, reach, behind, with_d=screen != "runs")
    plain = cli(work, argv)
    assert plain.code == 0, plain.text
    missing = missing_facts(plain.out, shown)
    assert missing == [], (screen, missing)


def test_tf19_3_home_carries_doctor_s_config_and_the_runs(work: Path) -> None:
    s = drive(work, [], size=TALL)
    shown = s.last.body_text()
    doctor = cli(work, ["doctor"]).out.splitlines()
    config = next(line for line in doctor if line.lstrip().startswith("config "))
    assert missing_facts(config.split("failures")[0], shown) == []
    runs = json.loads(cli(work, ["runs", "--json"]).out)["runs"]
    for run in runs:
        assert run["name"] in shown and run["run_id"] in shown and f"{run['rows']}" in shown, run


def test_tf19_3_imports_carries_the_runs_and_the_found_files(work: Path) -> None:
    from poisson_trace import api, core

    s = drive(work, ["i"], size=TALL)
    shown = s.last.body_text()
    from tf0_support import chdir

    with chdir(work):
        listing = api.runs("jstore")
    assert missing_facts(listing.to_markdown(), shown) == []
    for src in core.run_sources(work / "jstore"):
        assert src.tool in shown and all(f in shown for f in src.files)
    for f in core.found_results(work, store="jstore"):
        if not f.imported:
            assert name_shown(f.path, shown) and norm(f.said) in shown, f.path


# ---------- the summary and the caveats, whole ----------


@pytest.mark.parametrize("size", [(120, 40), (80, 24)], ids=["120x40", "80x24"])
@pytest.mark.parametrize("screen", ["run", "verdict compare", "verdict fix-check", "changes"])
def test_tf19_3_the_summary_and_the_caveats_whole(work: Path, screen: str, size: tuple[int, int]) -> None:
    reach, _behind, argv = SCREENS[screen]
    report = cli(work, argv).out
    views = _behind_m(work, reach, size)
    shown = " ".join(g.body_text() for g in views)
    shown = shown.replace("`", "")
    for label, text in summary_values(report):
        assert norm(f"{label} {text}") in shown, (label, text)
    caveats = section_lines(report, "Before you act on this")
    assert caveats
    for line in caveats:
        assert norm(line) in shown, line


@pytest.mark.parametrize("screen", ["verdict compare", "verdict fix-check"])
def test_tf19_3_at_80x24_the_overflow_is_behind_one_key(work: Path, screen: str) -> None:
    reach, _behind, argv = SCREENS[screen]
    views = _behind_m(work, reach, (80, 24))
    first = views[0]
    hint = [r for r in first.body if "more lines above the table: m shows them" in r]
    assert len(hint) == 1, first.text()
    n = int(hint[0].split()[0].replace(",", ""))
    assert n > 0
    assert "m" in first.keys()
    # the links block stays on screen
    assert first.line_starting("page"), first.text()
    # the verdict line stays first, with the command's word
    word = str(json.loads(cli(work, [*argv, "--json"]).out)["verdict"])
    assert first.body[0].startswith(f"  {word}  "), (first.body[0], word)


def test_tf19_3_at_80x24_the_compare_links_stay(work: Path) -> None:
    s = drive(work, ["c", "enter"], size=(80, 24))
    g = s.last
    assert g.line_starting("curves") and g.line_starting("page"), g.text()


# ---------- could not say ----------


@pytest.mark.parametrize("screen", ["verdict compare", "verdict fix-check", "changes"])
def test_tf19_3_could_not_say_whole(work: Path, screen: str) -> None:
    reach, _behind, argv = SCREENS[screen]
    report = cli(work, argv).out
    s = drive(work, [*reach, "d"], size=TALL)
    g = s.last
    assert g.title() == "could not say"
    shown = g.body_text()
    lines = section_lines(report, "What this cannot say")
    assert lines
    for line in lines:
        assert norm(line) in shown, line


IMPORTED_CONFIG = """\
version = 1

[store]
path = "../tables"

[events]
failed = ["missed"]

[check]
max_mde = 0.5
"""


def test_tf19_3_could_not_say_on_an_imported_store_carries_section_6_4(work: Path) -> None:
    """The app opened on a config naming the table store: the run screen of an imported run, and
    its could not say screen (``d``), which carries the report's "What this cannot say" whole and
    the sentence the report adds for a run with no traces; a fix-check of the two imports, whose could
    not say carries its report's lines whole."""
    (work / "imp").mkdir()
    (work / "imp" / "trace.toml").write_text(IMPORTED_CONFIG, encoding="utf-8")
    where = cli(work, ["where", "new", "--config", "imp/trace.toml"])
    assert where.code == 0, where.text
    sentence = next(line for line in where.out.splitlines() if line.startswith("This run has no traces"))
    s = drive(work, ["r", "enter", "<snap>", "d"], size=TALL, config="imp/trace.toml")
    run, g = s.grids[0], s.last
    assert run.title() == "run" and run.subject() == "new", run.text()
    assert norm(sentence) in run.body_text()
    assert g.title() == "could not say", g.text()
    for line in [*section_lines(where.out, "What this cannot say"), sentence]:
        assert norm(line) in g.body_text(), line
    fix = cli(work, ["fix-check", "old", "new", "--config", "imp/trace.toml", "--inputs", "all"])
    assert fix.code == 0, fix.text
    s = drive(work, ["f", "enter", "d"], size=TALL, config="imp/trace.toml")
    assert s.last.title() == "could not say"
    for line in section_lines(fix.out, "What this cannot say"):
        assert norm(line) in s.last.body_text(), line
