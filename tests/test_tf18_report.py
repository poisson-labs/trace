"""TF18-14 to TF18-16: ``poisson-trace report DIR``, the HTML report (spec section 17.3 item 8;
section 11.7 as amended; SB5).

**TF18-14** ``report DIR`` on a bundle ``--out`` wrote: writes ``report.html`` into it, then
rewrites ``handover.json`` with the new file's name, digest and size added to ``files`` and
everything else as it was; touches no other file of the bundle and no store. It prints its
verdict line, ``  wrote  DIR/report.html`` and a ``next:`` line (A14). A ``report.html`` that
is there is refused without ``--force`` and replaced with it; a bundle that fails the validator
is refused before anything is written, with the validator's words; a folder that is not a
bundle is the refusal ``handover --check`` gives; there is no ``--json`` (A14). ``--open`` opens
the page; ``handover --check`` then names ``report DIR --open`` as its next command (A12).

On a terminal, pretty and ``--plain`` at 80 columns, it prints the same words, ``ok`` green when
pretty, the written path whole on its line (TF18-23).

**TF18-15** The page is self-contained: one ``<style>`` holding Prove's ``style.css`` whole, the
charts inline, no ``<script>``, ``<link>``, ``<iframe>``, ``<object>`` or ``<embed>``, no ``src``,
no ``href`` but an anchor of the page, no attribute holding a scheme, the narrower policy
(A6), and its first ``<h1>`` the verdict line: section 11.7's checks. ``handover --check``
applies them: a bundle whose ``report.html`` breaks any one of them, re-listed with its new
digest, is ``not valid`` (exit 4), and the same bundle re-listed with no change is ``ok``.

**TF18-16** One renderer: ``report.html`` is the static UI's page for the bundle's artifact,
with the same title, verdict line, headings, facts and lines (a line of the page that holds
nothing but links to other pages apart), the same footer and generator, and every line of the
report.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tf0_support import REPO
from tf9_support import cells, runs_of, strip
from tf9_support import run as pty
from tf13_support import cli
from tf18_support import (
    REPORT_POLICY,
    SAVES,
    build_work,
    copy_work,
    measures_argv,
    missing_lines,
    pages_of,
    prove_bundle,
    read_file,
    recording_browser,
    redigest,
    report_lines,
    section_11_7,
    sha256,
    snapshot,
    ui,
    version,
)

BUNDLES = {"fb": "fix-check", "cb": "compare", "wb": "where after", "xb": "changes", "tb": "fix-check tables"}


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = build_work(tmp_path_factory.mktemp("tf18-report"))
    for folder, label in BUNDLES.items():
        ran = cli(work, [*SAVES[label][1], "--out", folder])
        assert ran.code == 0, ran.text
    return work


@pytest.fixture(scope="module")
def reported(base: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = copy_work(base, tmp_path_factory.mktemp("tf18-reported"))
    for folder in BUNDLES:
        ran = cli(work, ["report", folder])
        assert ran.code == 0, ran.text
    assert ui(work, "--config", "conf/trace.toml").code == 0
    return work


@pytest.fixture
def work(base: Path, tmp_path: Path) -> Path:
    return copy_work(base, tmp_path)


def handover(folder: Path) -> dict[str, object]:
    return json.loads((folder / "handover.json").read_text(encoding="utf-8"))


def result(folder: Path) -> dict[str, object]:
    return json.loads((folder / "result.json").read_text(encoding="utf-8"))


# ---------- TF18-14 ----------


@pytest.mark.parametrize("folder", list(BUNDLES))
def test_tf18_14_writes_the_page_and_lists_it(work: Path, folder: str) -> None:
    bundle = work / folder
    before = handover(bundle)
    files_before = snapshot(bundle)
    ran = cli(work, ["report", folder])
    assert ran.code == 0 and ran.err == "", ran.text
    lines = ran.out.splitlines()
    assert lines[0].startswith("ok  ") and lines[1] == f"  wrote  {folder}/report.html" and lines[-1].startswith("next: ")
    after = handover(bundle)
    data = (bundle / "report.html").read_bytes()
    entries = {e["name"]: e for e in after["files"]}  # type: ignore[index, union-attr]
    assert entries["report.html"] == {"name": "report.html", "sha256": sha256(data), "bytes": len(data)}
    assert [e for e in after["files"] if e["name"] != "report.html"] == before["files"]  # type: ignore[union-attr, index]
    names = [e["name"] for e in after["files"]]  # type: ignore[union-attr, index]
    assert names == sorted(names)
    assert {k: v for k, v in after.items() if k != "files"} == {k: v for k, v in before.items() if k != "files"}
    now = snapshot(bundle)
    assert {k: v for k, v in now.items() if k not in ("report.html", "handover.json")} == {k: v for k, v in files_before.items() if k != "handover.json"}


def test_tf18_14_touches_no_store(work: Path) -> None:
    stores = {s: snapshot(work / s) for s in ("store", "tables")}
    assert cli(work, ["report", "fb"]).code == 0
    assert {s: snapshot(work / s) for s in ("store", "tables")} == stores


def test_tf18_14_the_bundle_still_holds_what_it_promises(work: Path) -> None:
    assert cli(work, ["report", "fb"]).code == 0
    checked = cli(work, ["handover", "--check", "fb"])
    assert checked.code == 0 and checked.out.startswith("ok  ")
    assert checked.out.splitlines()[-1] == "next: poisson-trace report fb --open"


def test_tf18_14_a_page_that_is_there_needs_force(work: Path) -> None:
    assert cli(work, ["report", "fb"]).code == 0
    first = snapshot(work / "fb")
    again = cli(work, ["report", "fb"])
    assert again.code == 1 and again.out == "" and again.err.startswith("error: ")
    assert snapshot(work / "fb") == first
    forced = cli(work, ["report", "fb", "--force"])
    assert forced.code == 0, forced.text
    assert snapshot(work / "fb") == first


def test_tf18_14_a_bundle_that_fails_the_validator_is_refused_first(work: Path) -> None:
    with (work / "fb" / "result.json").open("ab") as f:
        f.write(b" ")
    before = snapshot(work / "fb")
    checked = cli(work, ["handover", "--check", "fb"])
    assert checked.code == 4 and checked.out.startswith("not valid  ")
    ran = cli(work, ["report", "fb"])
    assert ran.code == 1 and ran.out == ""
    assert ran.err.splitlines()[0] == "error: " + checked.out.splitlines()[0][len("not valid  "):]
    assert snapshot(work / "fb") == before


@pytest.mark.parametrize("folder", ["conf", "no-such"])
def test_tf18_14_a_folder_that_is_not_a_bundle(work: Path, folder: str) -> None:
    want = cli(work, ["handover", "--check", folder])
    got = cli(work, ["report", folder])
    assert want.code == 1
    assert (got.code, got.out, got.err.splitlines()[0]) == (1, "", want.err.splitlines()[0])


@pytest.mark.parametrize("argv,code", [(["report"], 2), (["report", "fb", "--json"], 2)])
def test_tf18_14_usage(work: Path, argv: list[str], code: int) -> None:
    ran = cli(work, argv)
    assert ran.code == code and ran.out == "" and ran.err.startswith("error: ")
    assert not (work / "fb" / "report.html").exists()


def test_tf18_14_open_opens_the_page(work: Path, tmp_path: Path) -> None:
    env, log = recording_browser(tmp_path)
    full = {**os.environ, "PYTHONPATH": str(REPO / "src"), **env}
    ran = subprocess.run([sys.executable, "-m", "poisson_trace", "report", "fb", "--open"], cwd=work, capture_output=True,
                         text=True, env=full, timeout=600)
    assert ran.returncode == 0, ran.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [(work / "fb" / "report.html").resolve().as_uri()]


def test_tf18_23_report_on_a_terminal(base: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    for i, extra in enumerate(([], ["--plain"])):
        work = copy_work(base, tmp_path, name=f"w{i}")
        piped = cli(copy_work(base, tmp_path, name=f"p{i}"), ["report", "fb"])
        ran = pty(["report", "fb", *extra], cwd=work, home=home, cols=80)
        assert ran.code == 0, (ran.out, ran.err)
        lines = [strip(line) for line in ran.out.splitlines() if strip(line).strip()]
        assert "  wrote  fb/report.html" in lines
        assert " ".join(strip(ran.out).split()) == " ".join(piped.out.split())
        if not extra:
            assert ("G", "ok") in runs_of(cells(ran.out)[0])


def test_tf18_14_help(work: Path) -> None:
    ran = cli(work, ["report", "--help"])
    assert ran.code == 0 and "--open" in ran.out and "--force" in ran.out and "examples:" in ran.out


# ---------- TF18-15 ----------


@pytest.mark.parametrize("folder", list(BUNDLES))
def test_tf18_15_section_11_7_holds(reported: Path, folder: str) -> None:
    page = read_file(reported / folder / "report.html")
    assert section_11_7(page, result(reported / folder)) == []  # type: ignore[arg-type]


@pytest.mark.parametrize("folder", list(BUNDLES))
def test_tf18_15_self_contained(reported: Path, folder: str) -> None:
    page = read_file(reported / folder / "report.html")
    assert page.policy == [REPORT_POLICY]
    styles = page.all("style")
    assert len(styles) == 1 and prove_bundle()["style.css"].decode("utf-8") in styles[0].text
    assert all(h.startswith("#") for h in page.hrefs()), page.hrefs()
    assert page.srcs() == []
    assert not page.all("base") and not page.all("img") and not page.all("use")
    assert page.source.startswith('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n')


@pytest.mark.parametrize("folder,ident", [("wb", "curve"), ("cb", "curves"), ("cb", "hazard-ratio")])
def test_tf18_15_the_charts_inline(reported: Path, folder: str, ident: str) -> None:
    fig = read_file(reported / folder / "report.html").inside(ident)
    assert fig.all("svg") and fig.all("table")


BREAKS = {
    "a script": ("</body>", "<script>1</script></body>"),
    "a stylesheet link": ("</head>", '<link rel="stylesheet" href="x.css"></head>'),
    "a frame": ("</body>", "<iframe></iframe></body>"),
    "an object": ("</body>", "<object></object></body>"),
    "an embed": ("</body>", "<embed></body>"),
    "a scheme": ("</body>", '<a href="https://example.invalid/">x</a></body>'),
    "a scheme in another attribute": ("</body>", '<p title="javascript:1">x</p></body>'),
    "another first heading": ("<h1", "<h1>ok  something else</h1><h1"),
}


@pytest.mark.parametrize("what", ["unchanged", *BREAKS])
def test_tf18_15_handover_check_applies_them(reported: Path, tmp_path: Path, what: str) -> None:
    work = copy_work(reported, tmp_path)
    page = work / "fb" / "report.html"
    if what != "unchanged":
        old, new = BREAKS[what]
        text = page.read_text(encoding="utf-8")
        assert old in text
        page.write_text(text.replace(old, new, 1), encoding="utf-8")
    redigest(work / "fb", "report.html")
    ran = cli(work, ["handover", "--check", "fb"])
    if what == "unchanged":
        assert ran.code == 0 and ran.out.startswith("ok  "), ran.text
    else:
        assert ran.code == 4 and ran.out.startswith("not valid  "), (what, ran.text)


def test_tf18_15_a_page_not_listed_is_not_valid(reported: Path, tmp_path: Path) -> None:
    work = copy_work(reported, tmp_path)
    with (work / "fb" / "report.html").open("ab") as f:
        f.write(b" ")
    ran = cli(work, ["handover", "--check", "fb"])
    assert ran.code == 4 and ran.out.startswith("not valid  ")


# ---------- TF18-16 ----------


def _static(work: Path, folder: str) -> Path:
    art = json.loads((work / folder / "artifact.json").read_text(encoding="utf-8"))
    store = SAVES[BUNDLES[folder]][0]
    return pages_of(work / store) / art["kind"] / f"{art['id']}.html"


@pytest.mark.parametrize("folder", list(BUNDLES))
def test_tf18_16_the_report_is_the_static_page(reported: Path, folder: str) -> None:
    report = read_file(reported / folder / "report.html")
    static = read_file(_static(reported, folder))
    assert report.h1 == static.h1
    assert report.title == static.title
    it_h = iter(report.headings())
    assert all(any(h == r for r in it_h) for h in static.headings()), (static.headings(), report.headings())
    assert report.footer == static.footer
    assert report.generator == static.generator == [f"poisson-trace {version()}"]
    facts = lambda p: sorted((e.attrs["data-fact"], e.attrs.get("data-value")) for e in p.elements if "data-fact" in e.attrs)  # noqa: E731
    assert facts(report) == facts(static)
    links = {e.text.strip() for p in (report, static) for e in p.all("a") if e.text.strip()}

    def only_links(block: str) -> bool:
        for text in sorted(links, key=len, reverse=True):
            block = block.replace(text, "")
        return not block.replace("·", "").replace("|", "").strip()

    lines = [b for b in static.blocks if not only_links(b)]
    it = iter(report.blocks)
    assert all(any(b == r for r in it) for b in lines), [b for b in lines if b not in report.blocks]


@pytest.mark.parametrize("folder", list(BUNDLES))
def test_tf18_16_every_line_of_the_report(reported: Path, folder: str) -> None:
    page = read_file(reported / folder / "report.html")
    assert missing_lines(page, report_lines((reported / folder / "report.md").read_text(encoding="utf-8"))) == []
    ran = cli(reported, measures_argv(SAVES[BUNDLES[folder]][1]))
    assert missing_lines(page, report_lines(ran.out)) == []
