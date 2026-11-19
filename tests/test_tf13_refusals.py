"""TF13-19 to TF13-23: errors and refusals come through the API as ``api.Refusal``, carrying the
sentence, the next commands, the exit code and the notes the command line prints.

TF13-19: every refusal of the main command's verbs after the command line is read, through the
API: the same sentence (``error: <sentence>``), the same ``next:`` commands, the same exit code
(1, or 2 for what a verb needs and no flag or config gives), the same notes before it; nothing
printed and nothing written.

TF13-20: the same for the import.

TF13-21: the delivery's own refusals (``--svg`` and ``--out``) through the result's methods.

TF13-22 (slow): every refusal of TF0's corpus, the look's own, through the API. TF13-19 and
TF13-20 are its fast twins.

TF13-23: a refusal is an ``api.Refusal`` whatever raised it inside: a config's fault, a names
file's, Prove's, the reader's, the folder resolver's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tf13_support import (
    IMPORT_REFUSALS_ARGV, REFUSALS_ARGV, VERBS_ARGV, api, attempt, call_for, cli, cli_import, error_of,
    import_call_for, notes_of, snapshot, workspace,
)


def _same_refusal(got: Any, ran: Any, label: str) -> None:
    assert got.out == got.err == "", (label, got.out, got.err)
    assert got.refusal is not None, (label, "no refusal", got.result)
    e = got.refusal
    message, nexts = error_of(ran.err)
    assert e.message == str(e) == message, label
    assert tuple(e.next) == nexts, label
    assert e.exit_code == ran.code, label
    assert tuple(e.notes) == notes_of(ran.err), label


# ---------- TF13-19 ----------


@pytest.mark.parametrize("label", list(REFUSALS_ARGV))
def test_tf13_19_every_refusal_of_the_verbs_through_the_api(tmp_path: Path, label: str) -> None:
    argv, code = REFUSALS_ARGV[label]
    work = workspace(tmp_path)
    ran = cli(work, argv)
    assert ran.code == code and ran.out == "", ran.text
    before = snapshot(work)
    got = attempt(call_for(argv), work)
    _same_refusal(got, ran, label)
    assert snapshot(work) == before, "nothing written"


# ---------- TF13-20 ----------


@pytest.mark.parametrize("label", list(IMPORT_REFUSALS_ARGV))
def test_tf13_20_every_refusal_of_the_import_through_the_api(tmp_path: Path, label: str) -> None:
    argv, code = IMPORT_REFUSALS_ARGV[label]
    work = workspace(tmp_path)
    ran = cli_import(work, argv)
    assert ran.code == code and ran.out == "", ran.text
    before = snapshot(work)
    got = attempt(import_call_for(argv), work)
    _same_refusal(got, ran, label)
    assert snapshot(work) == before, "nothing written"


# ---------- TF13-21 ----------


DELIVERY_REFUSALS = {
    "an SVG into a folder that is not there": (["--svg", "no-such-dir/curve.svg"], lambda r: r.write_svg("no-such-dir/curve.svg")),
    "an SVG over a file": (["--svg", "grades.csv"], lambda r: r.write_svg("grades.csv")),
    "an SVG onto a folder": (["--svg", "conf"], lambda r: r.write_svg("conf")),
    "a bundle over a folder that is there": (["--out", "conf"], lambda r: r.to_bundle("conf")),
}


@pytest.mark.parametrize("label", list(DELIVERY_REFUSALS))
def test_tf13_21_the_deliverys_own_refusals(tmp_path: Path, label: str) -> None:
    extra, deliver = DELIVERY_REFUSALS[label]
    work = workspace(tmp_path)
    ran = cli(work, [*VERBS_ARGV["where"], *extra])
    assert ran.code == 1 and ran.out == "", ran.text
    result = attempt(call_for(VERBS_ARGV["where"]), work).result
    before = snapshot(work)
    got = attempt(lambda: deliver(result), work)
    _same_refusal(got, ran, label)
    assert snapshot(work) == before


def test_tf13_21_a_a_run_with_no_traces_has_no_curve_to_write(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    argv = VERBS_ARGV["where untraced"]
    ran = cli(work, [*argv, "--svg", "curve.svg"])
    assert ran.code == 1, ran.text
    result = attempt(call_for(argv), work).result
    got = attempt(lambda: result.write_svg("curve.svg"), work)
    _same_refusal(got, ran, "no traces, no curve")
    got = attempt(lambda: result.to_svg(), work)
    assert got.refusal is not None and got.refusal.message == error_of(ran.err)[0]
    assert not (work / "curve.svg").exists()


# ---------- TF13-22 ----------


@pytest.mark.slow
def test_tf13_22_every_refusal_of_the_looks_corpus_through_the_api(tmp_path: Path) -> None:
    from tf0_support import chdir, corpus, prepare, run_item

    work = prepare(tmp_path / "corpus")
    for item in corpus():
        if item.kind != "refusal":
            continue
        with chdir(work):
            ran = run_item(item)
        assert ran.code == item.expect == 1, item.label
        argv = [w for w in item.argv if w != "--json"]
        if item.command == "trace":
            call = call_for(argv)
        else:
            call = import_call_for(argv)
        got = attempt(call, work)
        _same_refusal(got, ran, item.label)


# ---------- TF13-23 ----------


def test_tf13_23_whatever_refuses_inside_comes_out_as_a_refusal(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    a = api()
    # a config that is not one (the config's own fault, naming its line)
    (work / "conf" / "bad.toml").write_text('version = 1\n[store]\npath = "../store"\n[events]\nfailed = "violated"\n', encoding="utf-8")
    # a names file that is not one
    (work / "store" / "trace-names.toml").write_text("this is not toml = = \n", encoding="utf-8")
    cases: dict[str, tuple[list[str], Any]] = {
        "a config's fault": (["where", "agent after", "--config", "conf/bad.toml"],
                             lambda: a.where(None, "agent after", config="conf/bad.toml")),
        "a names file's fault": (["where", "agent after", "--store", "store", "--event", "violated"],
                                 lambda: a.where("store", "agent after", event=["violated"])),
        "a names file's fault, through runs": (["runs", "--store", "store"], lambda: a.runs("store")),
        "a folder of two runs": (["where", "store", "--event", "violated"], lambda: a.where(None, "store", event=["violated"])),
    }
    for label, (argv, fn) in cases.items():
        ran = cli(work, argv)
        assert ran.code in (1, 2) and ran.out == "", (label, ran.text)
        _same_refusal(attempt(fn, work), ran, label)
    # a reader's refusal of a file it cannot read, through the import
    (work / "files" / "broken.xml").write_text("<testsuite><testcase", encoding="utf-8")
    ran = cli_import(work, ["junit", "files/broken.xml", "--store", "new-store", "--run", "b"])
    assert ran.code == 1, ran.text
    _same_refusal(attempt(lambda: a.import_run("new-store", "junit", ["files/broken.xml"], run="b"), work), ran, "a reader's refusal")
    assert not (work / "new-store").exists()
