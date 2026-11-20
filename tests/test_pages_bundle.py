"""TF18-8 to TF18-12: what every page is made of, what it may load, what it never touches, and
when it is built (``docs/cli-look.md``, "The static UI").

**TF18-8** The fixed files are the installed Prove's UI bundle byte for byte: ``style.css`` and
``ui.js`` (the colour tokens are in ``style.css``; Prove's bundle has no third file), copied from
the installed ``poisson_prove``, whichever Prove at or above Trace's floor that is.

**TF18-9** Every page is Prove's skeleton: the doctype, ``lang="en"``, the charset first, Prove's
Content-Security-Policy meta, the viewport, the generator ``poisson-trace <version>``, the header
(``poisson-trace``, the store's folder name), and Prove's footer with Trace's name and the
page's own address inside the UI. The parser reports no error.

**TF18-10** Nothing from the network: every ``href`` and ``src`` is a relative path to a file that
is there (a page, the fixed files, Prove's index, another store's pages) or an anchor of the page;
no attribute holds a scheme but ``data:``; the one script is ``ui.js`` and the one stylesheet
``style.css``; no ``@import`` and no ``url(`` in an inline style; every table there whole in the
HTML, so the page works with the script off.

**TF18-11** Trace never writes, rebuilds or deletes Prove's pages: with Prove's dashboard built,
``ui`` and every save leave every file outside ``ui/trace/`` byte for byte; with none built,
Trace makes no page outside ``ui/trace/``. With ``ui/trace/`` gone after Prove's own rebuild,
``ui`` puts it back and leaves Prove's files as they were.

**TF18-12** When the pages are built: by ``ui``; by every command that saves (``--save`` on each
counting verb, ``--out``, ``api.save``, ``to_bundle``), a store with no pages included;
not by a verb that saves nothing. A save whose pages cannot be written prints one ``note:`` and
keeps its exit code and stdout.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from look_support import chdir
from api_support import api, cli
from pages_support import (
    BUNDLE,
    PROVE_POLICY,
    SAVES,
    SCHEME,
    artifacts,
    build_work,
    copy_work,
    expected_files,
    files_under,
    pages_of,
    prove_bundle,
    read_file,
    resolve,
    snapshot,
    ui,
    ui_root,
    version,
)


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_work(tmp_path_factory.mktemp("tf18-bundle"))


@pytest.fixture(scope="module")
def built(base: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = copy_work(base, tmp_path_factory.mktemp("tf18-bundle-built"))
    ran = ui(work, "--config", "conf/trace.toml")
    assert ran.code == 0, ran.text
    return work


def all_pages(work: Path) -> list[Path]:
    return sorted(p for store in ("store", "tables") for p in pages_of(work / store).rglob("*.html"))


# ---------- TF18-8 ----------


@pytest.mark.parametrize("store", ["store", "tables"])
def test_tf18_8_the_fixed_files_are_proves_byte_for_byte(built: Path, store: str) -> None:
    for name, data in prove_bundle().items():
        assert (pages_of(built / store) / name).read_bytes() == data, name


# ---------- TF18-9 ----------


def _address(work: Path, path: Path) -> str:
    for store in ("store", "tables"):
        ui_dir = ui_root(work / store)
        if ui_dir in path.parents:
            return str(path.relative_to(ui_dir))
    raise AssertionError(path)


def test_tf18_9_every_page_is_proves_skeleton(built: Path) -> None:
    pages = all_pages(built)
    assert len(pages) == sum(len(expected_files(built / s)) - len(BUNDLE) for s in ("store", "tables"))
    for path in pages:
        text = path.read_text(encoding="utf-8")
        page = read_file(path)
        assert text.startswith('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'), path
        assert page.errors == [], (path, page.errors)
        assert page.policy == [PROVE_POLICY], path
        assert page.generator == [f"poisson-trace {version()}"], path
        assert page.meta(name="viewport") == ["width=device-width, initial-scale=1"], path
        address = _address(built, path)
        assert page.footer == f"Built by poisson-trace from the store. Nothing was loaded from the network. Address: {address}", path
        header = page.first("header")
        assert header is not None
        tool = [e for e in page.elements if e.tag == "span" and "tool" in e.attrs.get("class", "").split() and "header" in e.parents]
        store = [e for e in page.elements if e.tag == "span" and "store" in e.attrs.get("class", "").split() and "header" in e.parents]
        assert [e.text for e in tool] == ["poisson-trace"], path
        folder = "store" if (built / "store") in path.parents else "tables"
        assert [e.text.strip() for e in store] == [folder], path


# ---------- TF18-10 ----------


def test_tf18_10_every_reference_is_a_file_that_is_there(built: Path) -> None:
    allowed = [pages_of(built / "store").resolve(), pages_of(built / "tables").resolve()]
    for path in all_pages(built):
        page = read_file(path)
        for e in page.elements:
            for k, v in e.attrs.items():
                if SCHEME.match(v) and not (k in ("src", "href") and v.startswith("data:")) and k != "xmlns" and not k.startswith("xmlns:"):
                    raise AssertionError(f"{path}: {e.tag} {k}={v}")
        for tag in ("a", "link", "script", "img", "iframe", "object", "embed", "source", "use", "image"):
            for e in page.all(tag):
                for k in ("href", "src", "data", "xlink:href"):
                    v = e.attrs.get(k)
                    if v is None or v.startswith("#") or v.startswith("data:"):
                        continue
                    target = resolve(path, v)
                    assert target is not None and target.is_file(), (path, v)
                    assert any(a in target.resolve().parents for a in allowed) or target.resolve() == (ui_root(built / "store") / "index.html").resolve(), (path, v)


def test_tf18_10_one_script_one_stylesheet_both_the_fixed_files(built: Path) -> None:
    for path in all_pages(built):
        page = read_file(path)
        scripts = page.all("script")
        assert len(scripts) == 1 and scripts[0].text.strip() == "", path
        assert resolve(path, scripts[0].attrs["src"]).resolve() == (path_store(built, path) / "ui.js").resolve(), path
        links = page.all("link")
        assert len(links) == 1 and links[0].attrs.get("rel") == "stylesheet", path
        assert resolve(path, links[0].attrs["href"]).resolve() == (path_store(built, path) / "style.css").resolve(), path
        for e in page.all("style"):
            assert "@import" not in e.text and not re.search(r"url\(\s*['\"]?(?!data:|#)", e.text), path
        for e in page.elements:
            style = e.attrs.get("style", "")
            assert "@import" not in style and not re.search(r"url\(\s*['\"]?(?!data:|#)", style), path
        assert not page.all("iframe") and not page.all("object") and not page.all("embed") and not page.all("base")


def path_store(work: Path, path: Path) -> Path:
    return next(pages_of(work / s) for s in ("store", "tables") if pages_of(work / s) in path.parents)


def test_tf18_10_the_tables_are_in_the_html(built: Path) -> None:
    for path in all_pages(built):
        page = read_file(path)
        for table in page.all("table"):
            if "data-sort" in table.attrs:
                assert table.attrs.get("id"), path
        assert "<template" not in page.source, path


# ---------- TF18-11 ----------


def _prove_ui(store: Path) -> None:
    exe = Path(sys.executable).with_name("poisson-prove")
    ran = subprocess.run([str(exe), "ui", "--store", str(store)], capture_output=True, text=True, timeout=600)
    assert ran.returncode == 0, ran.stdout + ran.stderr


@pytest.fixture
def with_prove(base: Path, tmp_path: Path) -> Path:
    work = copy_work(base, tmp_path)
    _prove_ui(work / "store")
    assert (ui_root(work / "store") / "index.html").is_file()
    return work


def test_tf18_11_ui_leaves_proves_pages_as_they_were(with_prove: Path) -> None:
    root = ui_root(with_prove / "store")
    before = snapshot(root, skip="trace")
    ran = ui(with_prove, "--config", "conf/trace.toml")
    assert ran.code == 0, ran.text
    assert snapshot(root, skip="trace") == before
    assert files_under(pages_of(with_prove / "store")) == expected_files(with_prove / "store")


@pytest.mark.parametrize("label", ["where after", "compare", "fix-check", "changes"])
def test_tf18_11_a_save_leaves_proves_pages_as_they_were(with_prove: Path, label: str) -> None:
    root = ui_root(with_prove / "store")
    before = snapshot(root, skip="trace")
    ran = cli(with_prove, [*SAVES[label][1], "--save"])
    assert ran.code == 0, ran.text
    assert snapshot(root, skip="trace") == before


def test_tf18_11_with_no_dashboard_trace_makes_only_its_own(base: Path, tmp_path: Path) -> None:
    work = copy_work(base, tmp_path)
    assert not ui_root(work / "store").exists()
    assert ui(work, "--store", "store").code == 0
    assert sorted(os.listdir(ui_root(work / "store"))) == ["trace"]


def test_tf18_11_after_proves_rebuild_ui_puts_traces_pages_back(base: Path, tmp_path: Path) -> None:
    work = copy_work(base, tmp_path)
    assert ui(work, "--store", "store").code == 0
    assert (pages_of(work / "store") / "index.html").is_file()
    _prove_ui(work / "store")
    # Prove's rebuild may swap in a whole new ui/; gone either way, whatever the installed Prove does
    shutil.rmtree(pages_of(work / "store"), ignore_errors=True)
    before = snapshot(ui_root(work / "store"))
    assert ui(work, "--store", "store").code == 0
    assert files_under(pages_of(work / "store")) == expected_files(work / "store")
    assert snapshot(ui_root(work / "store"), skip="trace") == before


# ---------- TF18-12 ----------


@pytest.mark.parametrize("label", list(SAVES))
def test_tf18_12_a_save_builds_the_pages(base: Path, tmp_path: Path, label: str) -> None:
    work = copy_work(base, tmp_path)
    shutil.rmtree(work / SAVES[label][0] / ".poisson" / "artifacts")
    assert not ui_root(work / SAVES[label][0]).exists()
    ran = cli(work, [*SAVES[label][1], "--save"])
    assert ran.code == 0, ran.text
    store = work / SAVES[label][0]
    assert files_under(pages_of(store)) == expected_files(store)
    assert sum(len(v) for v in artifacts(store).values()) == 1


@pytest.mark.parametrize("label", ["where after", "fix-check"])
def test_tf18_12_out_builds_the_pages(base: Path, tmp_path: Path, label: str) -> None:
    work = copy_work(base, tmp_path)
    ran = cli(work, [*SAVES[label][1], "--out", "bundle"])
    assert ran.code == 0, ran.text
    assert files_under(pages_of(work / "store")) == expected_files(work / "store")


def test_tf18_12_a_new_save_is_on_the_runs_page(base: Path, tmp_path: Path) -> None:
    work = copy_work(base, tmp_path)
    assert ui(work, "--store", "store").code == 0
    argv = ["fix-check", "agent before", "agent after", "--store", "store", "--event", "violated", "--inputs", "all", "--max-mde", "0.3"]
    ran = cli(work, [*argv, "--save", "--json"])
    assert ran.code == 0, ran.text
    kind, ident = json.loads(ran.out)["saved"].split("/")[-2:]
    assert f"{kind}/{ident}.html" in read_file(pages_of(work / "store") / "index.html").hrefs()
    assert (pages_of(work / "store") / kind / f"{ident}.html").is_file()


def test_tf18_12_the_api_save_and_to_bundle_build_the_pages(base: Path, tmp_path: Path) -> None:
    for how in ("save", "to_bundle"):
        work = copy_work(base, tmp_path, name=how)
        shutil.rmtree(work / "store" / ".poisson" / "artifacts")
        with chdir(work):
            r = api().fix_check("store", "agent before", "agent after", event=["violated", "timeout"], inputs="all", max_mde=0.1)
            if how == "save":
                api().save(r)
            else:
                r.to_bundle("bundle")
        assert files_under(pages_of(work / "store")) == expected_files(work / "store"), how


@pytest.mark.parametrize("argv", [
    ["where", "agent after", "--store", "store", "--event", "violated"],
    ["fix-check", "agent before", "agent after", "--store", "store", "--event", "violated", "--inputs", "all", "--max-mde", "0.3"],
    ["runs", "--store", "store"],
    ["handover", "--check", "nothing"],
])
def test_tf18_12_a_verb_that_saves_nothing_builds_nothing(base: Path, tmp_path: Path, argv: list[str]) -> None:
    work = copy_work(base, tmp_path)
    cli(work, argv)
    assert not ui_root(work / "store").exists()


def test_tf18_12_pages_that_cannot_be_written_are_a_note(base: Path, tmp_path: Path) -> None:
    work = copy_work(base, tmp_path)
    plain_work = copy_work(base, tmp_path, name="plain")
    argv = [*SAVES["fix-check"][1], "--save"]
    (work / "store" / ".poisson" / "ui").write_text("not a folder\n", encoding="utf-8")
    ran = cli(work, argv)
    want = cli(plain_work, argv)
    assert (ran.code, ran.out) == (want.code, want.out)
    notes = [line for line in ran.err.splitlines() if line.startswith("note: ")]
    assert [line for line in ran.err.splitlines() if line not in want.err.splitlines()] == notes[-1:]
    assert len(notes) == len([line for line in want.err.splitlines() if line.startswith("note: ")]) + 1
    assert notes[-1].startswith("note: the pages were not rebuilt: "), ran.err
