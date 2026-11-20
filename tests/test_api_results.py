"""TF13-8 to TF13-18: the typed results carry everything the command line prints and saves.

TF13-8: every invocation of the corpus, through the API, gives a result whose ``to_json()`` is
the ``--json`` stdout and whose ``to_markdown()`` is the plain stdout, byte for byte, with the
command's exit code and its ``note:`` lines as ``notes``; the API prints nothing.

TF13-9: the result is a frozen dataclass of the expected type, each ``--json`` key an attribute
holding what the JSON holds (``note`` as a list); and it keeps working after
the process changes folder.

TF13-10: each counting verb's result carries every key of the ``result.json`` its bundle holds,
TF6's failure-type diff and continuous measures among them, and the artifact's ``settings``.

TF13-11: ``save``, ``to_bundle`` and ``write_svg`` are ``--save``, ``--out`` and ``--svg``: the
same output, and the same files written.

TF13-12: ``import_run`` is the import, for each reader: the same output and the same run written.

TF13-13: ``name``, ``list_names`` and ``forget_name`` are the three forms of ``name``.

TF13-14: an ``api.Store`` serves as ``--store`` does, and sees a name given through it.

TF13-15: an ``api.Config`` (or the path given to ``--config``) serves as ``--config`` does.

TF13-16: ``load_bundle`` and ``validate_bundle`` read a bundle as ``handover --check`` does.

TF13-17: runs given as folders, with a reader's flags as keywords (TF22).

TF13-18: ``commands.doctor`` and ``commands.init`` are ``doctor`` and ``init``.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from api_support import (
    COUNTING, EV, IMPORT_ARGV, RESULT_JSON_ADDS, RESULT_TYPES, SCHEMAS, SLOW_IMPORTS, TWO_RUN_ADDS,
    VERBS_ARGV, api, attempt, call_for, cli, cli_import, commands, error_of, import_call_for, jsonable,
    notes_of, snapshot, workspace,
)
from look_support import chdir

ARMS = {"compare": ("a", "b"), "fix-check": ("old", "new"), "changes": ("a", "b")}


def _through_api(work: Path, argv: list[str], *, json_: bool | None = None) -> Any:
    call = call_for(argv)
    got = attempt(call, work)
    assert got.out == "" and got.err == "", (argv, got.out, got.err)
    assert got.refusal is None, (argv, got.refusal)
    return got.result


# ---------- TF13-8 ----------


@pytest.mark.parametrize("label", list(VERBS_ARGV))
def test_tf13_8_every_invocation_through_the_api_prints_what_the_command_line_prints(tmp_path: Path, label: str) -> None:
    work = workspace(tmp_path)
    argv = VERBS_ARGV[label]
    plain, as_json = cli(work, argv), cli(work, [*argv, "--json"])
    assert plain.code == as_json.code == 0, plain.text + as_json.text
    r = _through_api(work, argv)
    assert r.to_markdown() == plain.out, label
    assert r.to_json() == as_json.out, label
    assert r.exit_code == plain.code
    assert tuple(r.notes) == notes_of(plain.err) == notes_of(as_json.err), label


# ---------- TF13-9 ----------


@pytest.mark.parametrize("label", list(VERBS_ARGV))
def test_tf13_9_the_result_is_typed_and_holds_each_key_of_its_json(tmp_path: Path, label: str) -> None:
    work = workspace(tmp_path)
    argv = VERBS_ARGV[label]
    r = _through_api(work, argv)
    fn = call_for(argv).function
    a = api()
    assert type(r).__name__ == RESULT_TYPES[fn] and getattr(a, RESULT_TYPES[fn]) is type(r)
    assert dataclasses.is_dataclass(r) and type(r).__dataclass_params__.frozen  # type: ignore[attr-defined]
    doc = json.loads(r.to_json())
    assert doc["schema"] == SCHEMAS[fn]
    for key, value in doc.items():
        got = jsonable(getattr(r, key))
        if key == "note" and isinstance(value, str):
            # note is a list; where's --json keeps the one string it prints
            assert got[:1] == [value], (label, got)
        else:
            assert got == value, (label, key)


@pytest.mark.parametrize("label", ["where", "fix-check verdicts", "changes config name", "runs"])
def test_tf13_9_a_a_result_keeps_working_after_the_folder_changes(tmp_path: Path, label: str) -> None:
    """Read inside the workspace and outside it, a result gives the same: what the call read
    by a relative path stays the path the call read."""
    work = workspace(tmp_path)
    argv = VERBS_ARGV[label]
    r = _through_api(work, argv)
    with chdir(work):
        inside = {k: jsonable(getattr(r, k)) for k in json.loads(r.to_json())}
        extra = {k: jsonable(getattr(r, k)) for k in (*RESULT_JSON_ADDS, *TWO_RUN_ADDS, "settings")
                 if argv[0] in COUNTING and (k not in TWO_RUN_ADDS or argv[0] != "where")}
        texts = (r.to_json(), r.to_markdown())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with chdir(elsewhere):
        assert {k: jsonable(getattr(r, k)) for k in inside} == inside
        assert {k: jsonable(getattr(r, k)) for k in extra} == extra
        assert (r.to_json(), r.to_markdown()) == texts
        if argv[0] in COUNTING:
            bundled = r.to_bundle("bundle")
            assert bundled.to_markdown() == cli(work, [*argv, "--out", "bundle-cli"]).out.replace("bundle-cli", "bundle")
            assert (elsewhere / "bundle" / "result.json").is_file()


# ---------- TF13-10 ----------


@pytest.mark.parametrize("label", [k for k in VERBS_ARGV if VERBS_ARGV[k][0] in COUNTING])
def test_tf13_10_a_counting_result_carries_what_its_bundle_saves(tmp_path: Path, label: str) -> None:
    work = workspace(tmp_path)
    argv = VERBS_ARGV[label]
    ran = cli(work, [*argv, "--out", "bundle"])
    assert ran.code == 0, ran.text
    saved = json.loads((work / "bundle" / "result.json").read_text(encoding="utf-8"))
    artifact = json.loads((work / "bundle" / "artifact.json").read_text(encoding="utf-8"))
    clean = workspace(tmp_path, "clean")
    r = _through_api(clean, argv)
    for key in RESULT_JSON_ADDS:
        assert key in saved, (label, key)
    if argv[0] != "where":
        for key in TWO_RUN_ADDS:
            assert key in saved, (label, key)
    for key, value in saved.items():
        if key == "saved":
            assert r.saved is None, "not saved until saved"
            continue
        assert jsonable(getattr(r, key)) == value, (label, key)
    assert jsonable(r.settings) == artifact["settings"], label


# ---------- TF13-11 ----------


def _bundle_files(folder: Path) -> dict[str, Any]:
    """A bundle's files, with the two times that differ from one writing to the next left out."""
    out: dict[str, Any] = {}
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(folder).as_posix()
        if rel in ("handover.json", "artifact.json"):
            doc = json.loads(p.read_text(encoding="utf-8"))
            doc.pop("written_at", None)
            doc.pop("created_at", None)
            if rel == "handover.json":
                doc["files"] = [{k: v for k, v in f.items() if f["name"] != "artifact.json" or k == "name"} for f in doc["files"]]
            out[rel] = doc
        else:
            out[rel] = p.read_bytes()
    return out


def _artifacts(store: Path) -> dict[str, Any]:
    base = store / ".poisson" / "artifacts"
    return {p.parent.name + "/" + p.name: _bundle_files(p) for p in sorted(base.glob("*/*")) if p.is_dir()} if base.is_dir() else {}


@pytest.mark.parametrize("verb", COUNTING)
def test_tf13_11_save_is_the_save_option(tmp_path: Path, verb: str) -> None:
    argv = {"where": VERBS_ARGV["where"], "compare": VERBS_ARGV["compare"],
            "fix-check": VERBS_ARGV["fix-check"], "changes": VERBS_ARGV["changes"]}[verb]
    by_cli, by_api = workspace(tmp_path, "cli"), workspace(tmp_path, "api")
    plain = cli(by_cli, [*argv, "--save"])
    as_json = cli(workspace(tmp_path, "cli-json"), [*argv, "--save", "--json"])
    a = api()
    got = attempt(lambda: a.save(call_for(argv)()), by_api)
    assert got.out == got.err == "" and got.refusal is None
    r = got.result
    assert type(r) is type(attempt(call_for(argv), workspace(tmp_path, "unsaved")).result)
    assert r.to_markdown() == plain.out and r.to_json() == as_json.out
    assert r.saved == json.loads(as_json.out)["saved"]
    assert _artifacts(by_api / "store") == _artifacts(by_cli / "store")


@pytest.mark.parametrize("verb", COUNTING)
def test_tf13_11_a_to_bundle_is_the_out_option(tmp_path: Path, verb: str) -> None:
    argv = {"where": VERBS_ARGV["where"], "compare": VERBS_ARGV["compare"],
            "fix-check": VERBS_ARGV["fix-check measures"], "changes": VERBS_ARGV["changes"]}[verb]
    by_cli, by_api = workspace(tmp_path, "cli"), workspace(tmp_path, "api")
    plain = cli(by_cli, [*argv, "--out", "bundle"])
    as_json = cli(workspace(tmp_path, "cli-json"), [*argv, "--out", "bundle", "--json"])
    assert plain.code == as_json.code == 0, plain.text
    got = attempt(lambda: call_for(argv)().to_bundle("bundle"), by_api)
    assert got.out == got.err == "" and got.refusal is None
    r = got.result
    assert r.to_markdown() == plain.out and r.to_json() == as_json.out
    assert _bundle_files(by_api / "bundle") == _bundle_files(by_cli / "bundle")
    assert _artifacts(by_api / "store") == _artifacts(by_cli / "store")
    # --out over a bundle that is there takes --force, as the command line does
    again = attempt(lambda: call_for(argv)().to_bundle("bundle", force=True), by_api)
    assert again.refusal is None and again.result.to_markdown() == cli(by_cli, [*argv, "--out", "bundle", "--force"]).out


def test_tf13_11_b_write_svg_is_the_svg_option(tmp_path: Path) -> None:
    argv = VERBS_ARGV["where"]
    by_cli, by_api = workspace(tmp_path, "cli"), workspace(tmp_path, "api")
    plain = cli(by_cli, [*argv, "--svg", "curve.svg"])
    assert plain.code == 0, plain.text
    got = attempt(lambda: call_for(argv)().write_svg("curve.svg"), by_api)
    assert got.refusal is None and got.out == got.err == ""
    assert got.result.to_markdown() == plain.out
    assert (by_api / "curve.svg").read_bytes() == (by_cli / "curve.svg").read_bytes()
    text = attempt(lambda: call_for(argv)().to_svg(), by_api).result
    assert text.encode("utf-8") == (by_cli / "curve.svg").read_bytes()
    forced = attempt(lambda: call_for(argv)().write_svg("curve.svg", force=True), by_api)
    assert forced.result.to_markdown() == cli(by_cli, [*argv, "--svg", "curve.svg", "--force"]).out


def test_tf13_11_c_every_delivery_at_once_prints_its_lines_in_the_command_lines_order(tmp_path: Path) -> None:
    argv = VERBS_ARGV["where"]
    by_cli, by_api = workspace(tmp_path, "cli"), workspace(tmp_path, "api")
    plain = cli(by_cli, [*argv, "--svg", "curve.svg", "--out", "bundle", "--save"])
    assert plain.code == 0, plain.text
    got = attempt(lambda: api().save(call_for(argv)().write_svg("curve.svg").to_bundle("bundle")), by_api)
    assert got.refusal is None and got.result.to_markdown() == plain.out
    verdicts = VERBS_ARGV["fix-check verdicts"]
    plain = cli(by_cli, [*verdicts, "--out", "vbundle"])
    got = attempt(lambda: call_for(verdicts)().to_bundle("vbundle"), by_api)
    assert got.refusal is None and got.result.to_markdown() == plain.out
    assert jsonable(got.result.verdicts) == json.loads(cli(by_cli, [*verdicts, "--json"]).out)["verdicts"]


def test_tf13_11_d_a_store_that_cannot_be_written_is_a_note_and_the_result_goes_on(tmp_path: Path) -> None:
    import os

    if os.geteuid() == 0:
        pytest.skip("a folder made unwritable stays writable to root")
    argv = VERBS_ARGV["fix-check"]
    by_cli, by_api = workspace(tmp_path, "cli"), workspace(tmp_path, "api")
    for w in (by_cli, by_api):
        (w / "store" / ".poisson").chmod(0o555)
    try:
        plain = cli(by_cli, [*argv, "--save"])
        got = attempt(lambda: api().save(call_for(argv)()), by_api)
    finally:
        for w in (by_cli, by_api):
            (w / "store" / ".poisson").chmod(0o755)
    assert plain.code == 0 and got.refusal is None and got.out == got.err == ""
    assert got.result.to_markdown() == plain.out and got.result.saved is None
    assert tuple(got.result.notes) == notes_of(plain.err) and notes_of(plain.err)


# ---------- TF13-12 ----------


@pytest.mark.parametrize("label", [pytest.param(k, marks=pytest.mark.slow) if k in SLOW_IMPORTS else k for k in IMPORT_ARGV])
def test_tf13_12_import_run_is_the_import(tmp_path: Path, label: str) -> None:
    argv = IMPORT_ARGV[label]
    by_cli, by_api, by_json = workspace(tmp_path, "cli"), workspace(tmp_path, "api"), workspace(tmp_path, "json")
    plain, as_json = cli_import(by_cli, argv), cli_import(by_json, [*argv, "--json"])
    assert plain.code == as_json.code == 0, plain.text
    call = import_call_for(argv)
    got = attempt(call, by_api)
    assert got.out == got.err == "" and got.refusal is None, got.refusal
    r = got.result
    assert type(r).__name__ == RESULT_TYPES["import_run"]
    assert r.to_markdown() == plain.out and r.to_json() == as_json.out and r.exit_code == 0
    assert tuple(r.notes) == notes_of(plain.err)
    for key, value in json.loads(as_json.out).items():
        assert jsonable(getattr(r, key)) == value, key
    # the same run written: the same files, the same rows
    assert sorted(snapshot(by_api / "new-store")) == sorted(snapshot(by_cli / "new-store"))
    from poisson_prove.store import Store

    run = json.loads(as_json.out)["run"]
    ours, theirs = Store(by_api / "new-store"), Store(by_cli / "new-store")
    assert ours.runs() == theirs.runs() == [run]
    assert ours.read(run, meta=True, trace="envelope").equals(theirs.read(run, meta=True, trace="envelope")), run


def test_tf13_12_a_import_run_takes_the_tool_from_a_folder(tmp_path: Path) -> None:
    by_cli, by_api = workspace(tmp_path, "cli"), workspace(tmp_path, "api")
    plain = cli_import(by_cli, ["files/junit-folder", "--store", "new-store"])
    assert plain.code == 0, plain.text
    got = attempt(lambda: api().import_run("new-store", None, ["files/junit-folder"]), by_api)
    assert got.refusal is None and got.result.to_markdown() == plain.out


# ---------- TF13-13 ----------


def test_tf13_13_the_three_forms_of_name(tmp_path: Path) -> None:
    by_cli, by_api = workspace(tmp_path, "cli"), workspace(tmp_path, "api")
    a = api()
    steps = [
        (["name", "agent after", "shipped", "--store", "store"], lambda: a.name("store", "agent after", "shipped")),
        (["name", "shipped", "shipped", "--store", "store"], lambda: a.name("store", "shipped", "shipped")),
        (["name", "--list", "--store", "store"], lambda: a.list_names("store")),
        (["where", "shipped", "--store", "store", *EV], lambda: a.where("store", "shipped", event=["violated", "timeout"])),
        (["name", "shipped", "--forget", "--store", "store"], lambda: a.forget_name("store", "shipped")),
        (["name", "--list", "--store", "store"], lambda: a.list_names("store")),
    ]
    for argv, fn in steps:
        ran = cli(by_cli, argv)
        got = attempt(fn, by_api)
        assert got.out == got.err == "" and got.refusal is None, (argv, got.refusal)
        assert got.result.to_markdown() == ran.out and got.result.exit_code == ran.code, argv
        if argv[0] == "name":
            assert type(got.result).__name__ == RESULT_TYPES["name"]
        assert snapshot(by_api / "store") == snapshot(by_cli / "store"), argv
    # a name it cannot take is refused as the command line refuses it
    ran = cli(by_cli, ["name", "agent after", "latest", "--store", "store"])
    got = attempt(lambda: a.name("store", "agent after", "latest"), by_api)
    assert ran.code == got.refusal.exit_code == 1
    assert (got.refusal.message, tuple(got.refusal.next)) == error_of(ran.err)


# ---------- TF13-14 ----------


def test_tf13_14_a_store_serves_as_the_store_option(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    a = api()
    got = attempt(lambda: a.open_store("store"), work)
    assert got.refusal is None and type(got.result).__name__ == "Store"
    store = got.result
    by_path = attempt(lambda: a.where("store", "agent after", event=["violated", "timeout"]), work).result
    by_store = attempt(lambda: a.where(store, "agent after", event=["violated", "timeout"]), work).result
    assert by_store.to_markdown() == by_path.to_markdown() and by_store.to_json() == by_path.to_json()
    assert by_store.to_markdown() == cli(work, ["where", "agent after", "--store", "store", *EV]).out
    named = attempt(lambda: a.name(store, "agent after", "shipped"), work)
    assert named.refusal is None
    seen = attempt(lambda: a.where(store, "shipped", event=["violated", "timeout"]), work)
    assert seen.refusal is None, "a name given through the store is seen through it"
    assert seen.result.to_markdown() == cli(work, ["where", "shipped", "--store", "store", *EV]).out
    missing = attempt(lambda: a.open_store("no-such-store"), work)
    ran = cli(work, ["runs", "--store", "no-such-store"])
    assert missing.refusal is not None and missing.refusal.exit_code == ran.code == 1
    assert (missing.refusal.message, tuple(missing.refusal.next)) == error_of(ran.err)


# ---------- TF13-15 ----------


def test_tf13_15_a_config_serves_as_the_config_option(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    a = api()
    got = attempt(lambda: a.load_config("conf/trace.toml"), work)
    assert got.refusal is None and type(got.result).__name__ == "Config"
    cfg = got.result
    assert cfg.store() == "store" and cfg.store("tables") == "tables"
    for label in ("where config", "fix-check config", "compare config", "changes config name"):
        argv = VERBS_ARGV[label]
        by_path = attempt(call_for(argv), work).result
        call = call_for(argv)
        by_object = attempt(lambda call=call: getattr(a, call.function)(*call.args, **{**call.kwargs, "config": cfg}), work).result
        assert by_object.to_markdown() == by_path.to_markdown() == cli(work, argv).out, label
    bad = attempt(lambda: a.load_config("conf/none.toml"), work)
    ran = cli(work, ["where", "agent after", "--config", "conf/none.toml"])
    assert bad.refusal is not None and bad.refusal.exit_code == ran.code
    assert (bad.refusal.message, tuple(bad.refusal.next)) == error_of(ran.err)
    (work / "conf" / "broken.toml").write_text("version = 1\n[store\n", encoding="utf-8")
    bad = attempt(lambda: a.load_config("conf/broken.toml"), work)
    ran = cli(work, ["where", "agent after", "--config", "conf/broken.toml"])
    assert bad.refusal is not None and (bad.refusal.message, bad.refusal.exit_code) == (error_of(ran.err)[0], ran.code)


# ---------- TF13-16 ----------


def test_tf13_16_a_bundle_read_back_and_checked(tmp_path: Path) -> None:
    work = workspace(tmp_path)
    a = api()
    assert cli(work, [*VERBS_ARGV["fix-check"], "--out", "bundle"]).code == 0
    got = attempt(lambda: a.load_bundle("bundle"), work)
    assert got.refusal is None and got.out == got.err == ""
    b = got.result
    assert type(b).__name__ == RESULT_TYPES["load_bundle"]
    assert b.verb == "fix-check"
    assert jsonable(b.result) == json.loads((work / "bundle" / "result.json").read_text(encoding="utf-8"))
    assert jsonable(b.handover) == json.loads((work / "bundle" / "handover.json").read_text(encoding="utf-8"))
    assert jsonable(b.artifact) == json.loads((work / "bundle" / "artifact.json").read_text(encoding="utf-8"))
    assert b.report == (work / "bundle" / "report.md").read_text(encoding="utf-8")
    check = attempt(lambda: a.validate_bundle("bundle"), work).result
    ran = cli(work, ["handover", "--check", "bundle"])
    assert type(check).__name__ == RESULT_TYPES["validate_bundle"]
    assert (check.verdict, check.exit_code, check.to_markdown()) == ("ok", ran.code, ran.out) and ran.code == 0
    # a file changed after it was written
    report = work / "bundle" / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\nan edit\n", encoding="utf-8")
    check = attempt(lambda: a.validate_bundle("bundle"), work).result
    ran = cli(work, ["handover", "--check", "bundle"])
    assert (check.verdict, check.exit_code, check.to_markdown()) == ("not valid", ran.code, ran.out) and ran.code == 4
    # not a bundle at all
    for folder in ("no-such-bundle", "conf", "grades.csv"):
        ran = cli(work, ["handover", "--check", folder])
        for fn in (a.validate_bundle, a.load_bundle):
            refused = attempt(lambda fn=fn, folder=folder: fn(folder), work).refusal
            assert refused is not None and refused.exit_code == ran.code == 1, folder
            assert (refused.message, tuple(refused.next)) == error_of(ran.err), folder


# ---------- TF13-17 ----------


def _folders(work: Path) -> None:
    for name, file in (("ja", "humaneval-a.xml"), ("jb", "humaneval-b.xml")):
        (work / "folders" / name).mkdir(parents=True)
        shutil.copy2(work / "files" / file, work / "folders" / name / file)
    for run in ("old", "new"):
        (work / "folders" / f"t-{run}").mkdir()
        shutil.copy2(work / f"{run}.csv", work / "folders" / f"t-{run}" / f"{run}.csv")


@pytest.mark.parametrize("argv,call", [
    (["fix-check", "folders/ja", "folders/jb", "--event", "missed", "--inputs", "all", "--max-mde", "0.1"],
     lambda a: a.fix_check(None, "folders/ja", "folders/jb", event=["missed"], inputs="all", max_mde=0.1)),
    (["changes", "folders/ja", "folders/jb", "--event", "missed"],
     lambda a: a.changes(None, "folders/ja", "folders/jb", event=["missed"])),
    (["where", "folders/ja", "--event", "missed"],
     lambda a: a.where(None, "folders/ja", event=["missed"])),
    (["fix-check", "folders/t-old", "folders/t-new", "--event", "missed", "--inputs", "all", "--max-mde", "0.5",
      "--case-column", "case", "--outcome-column", "outcome", "--failed", "failed"],
     lambda a: a.fix_check(None, "folders/t-old", "folders/t-new", event=["missed"], inputs="all", max_mde=0.5,
                           case_column="case", outcome_column="outcome", failed=["failed"])),
    (["fix-check", "store/20261104T162926Z-b4d5", "store/20261104T162928Z-1596", *EV, "--inputs", "all", "--max-mde", "0.2"],
     lambda a: a.fix_check(None, "store/20261104T162926Z-b4d5", "store/20261104T162928Z-1596", event=["violated", "timeout"], inputs="all", max_mde=0.2)),
], ids=["junit folders", "changes on folders", "where on a folder", "table folders with the reader's flags", "prove run folders"])
def test_tf13_17_runs_given_as_folders(tmp_path: Path, argv: list[str], call: Any) -> None:
    work = workspace(tmp_path)
    _folders(work)
    before = snapshot(work)
    plain, as_json = cli(work, argv), cli(work, [*argv, "--json"])
    assert plain.code == as_json.code == 0, plain.text
    got = attempt(lambda: call(api()), work)
    assert got.refusal is None and got.out == got.err == "", got.refusal
    assert got.result.to_markdown() == plain.out and got.result.to_json() == as_json.out
    assert snapshot(work) == before, "a folder's runs are read into a store that does not last"


# ---------- TF13-18 ----------


def _same_but_folder(text: str, folder: Path) -> str:
    return text.replace(str(folder.resolve()), "<WORK>").replace(str(folder), "<WORK>")


@pytest.mark.parametrize("given", [["--config", "conf/trace.toml"], []], ids=["a config given", "no config here"])
def test_tf13_18_doctor_is_the_doctor_command(tmp_path: Path, given: list[str]) -> None:
    work = workspace(tmp_path)
    plain, as_json = cli(work, ["doctor", *given]), cli(work, ["doctor", *given, "--json"])
    kwargs = {"config": given[1]} if given else {}
    with chdir(work):
        r = commands().doctor(**kwargs)
    assert r.to_markdown() == plain.out and r.to_json() == as_json.out
    assert r.exit_code == plain.code == as_json.code
    assert json.loads(r.to_json())["verdict"] == r.verdict


def test_tf13_18_a_init_is_the_init_command(tmp_path: Path) -> None:
    folders = []
    for name in ("cli", "api"):
        folder = tmp_path / name
        folder.mkdir()
        shutil.copytree(workspace(tmp_path, f"src-{name}") / "store", folder / "runs")
        folders.append(folder)
    by_cli, by_api = folders
    ran = cli(by_cli, ["init", "--yes", "--event", "violated", "--event", "timeout"])
    assert ran.code == 0, ran.text
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with chdir(by_api), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        r = commands().init(yes=True, event=["violated", "timeout"])
    assert out.getvalue() == "", "init's result is printed by the command line"
    assert _same_but_folder(err.getvalue(), by_api) == _same_but_folder(ran.err, by_cli)
    assert _same_but_folder(r.to_markdown(), by_api) == _same_but_folder(ran.out, by_cli)
    assert r.exit_code == ran.code
    assert (by_api / "trace.toml").read_bytes() == (by_cli / "trace.toml").read_bytes()
    # a second init without --force is refused, as the command line refuses it
    again = cli(by_cli, ["init", "--yes", "--event", "violated"])
    a = api()
    with chdir(by_api), contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(a.Refusal) as caught:
            commands().init(yes=True, event=["violated"])
    assert again.code == caught.value.exit_code
    assert _same_but_folder(caught.value.message, by_api) == _same_but_folder(error_of(again.err)[0], by_cli)
