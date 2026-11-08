"""TF18-1 to TF18-7: the static pages' views (spec section 17.3 item 7; the design's section 3;
DM7, DM8, DM10, DM11 and DM14; SV15).

The workspace is TF13's with seven verdicts saved (``tf18_support.SAVES``): on the Prove 0.1.3
store the design session's own (two where, a compare, a fix-check, a changes; the mockups'
ids), on the table store a fix-check and a changes whose runs hold tries with no outcome. Then
``poisson-trace ui --config conf/trace.toml``, from inside it.

**TF18-1** The files: ``<store>/.poisson/ui/trace/`` holds the index, the two fixed files, a page
and a could-not-say page per saved verdict of Trace's, and nothing else; the config's other
store gets its own; Prove's saved comparison gets no page of Trace's; ``ui/`` holds nothing of
Trace's outside ``trace/`` (A1).

**TF18-2** The runs page (``index.html``): the verdict line ``runs`` prints for the store as its
first heading; a row a run with ``runs``'s facts (number, name, id, target or the tool an import
came from, rows, failed, traces, started, status); a row a saved verdict, newest first, linking
to its page; a run's name linking to its newest where page (A8).

**TF18-3** A verdict page (fix-check, compare, changes and where): its first heading is the
verdict line, its title the report's title, and it shows every line the plain report prints, in
order, under the report's own headings in the report's order (DM14), the continuous-measures
section where ``fix-check --measures`` prints it (A4), "Failures by kind" with its tables and the
no-outcome sentence; the per-input table sortable with a filter box; what was saved; links to
its could-not-say page and to the runs page.

**TF18-4** The where page's curve: inline SVG with a hover title on every step, and the data
under it (A9).

**TF18-5** Compare's charts (SV15, DM7, DM8): the artifact carries ``charts/curves`` and
``charts/hazard-ratio`` (the SVG role ``chart``, its JSON beside it, as TF6 lists where's
curve); the curves are each run's ``where``
curve under compare's failures; the hazard ratio's data is the verdict's; on the page each is a
figure with its data as a table, the first run in ``before``, the second in ``after``, each with
its band, no colour of the four meanings.

**TF18-6** The could-not-say page of every verdict: the verdict line, everything the verdict
cannot say, what it could not have detected, a link back.

**TF18-7** The links between stores' pages (DM10) and to Prove's dashboard (DM11, A13).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tf13_support import cli
from tf18_support import (
    EV,
    KINDS,
    MEANING_CLASSES,
    MEANING_COLOURS,
    MOCKUP_IDS,
    SAVES,
    artifact_folder,
    artifacts,
    build_work,
    copy_work,
    expected_files,
    files_under,
    id_of,
    measures_argv,
    missing_lines,
    pages_of,
    read_file,
    report_lines,
    resolve,
    title_line,
    ui,
    ui_root,
    verdict_line,
)

PROVE_COMPARISON = "19197f1deb19b9e3"  # Prove's own saved comparison in the committed store


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = build_work(tmp_path_factory.mktemp("tf18-pages"))
    ran = ui(work, "--config", "conf/trace.toml")
    assert ran.code == 0, ran.text
    return work


@pytest.fixture(scope="module")
def ids(built: Path) -> dict[str, tuple[str, str, str]]:
    return {label: id_of(built, label) for label in SAVES}


def result_of(work: Path, store: str, kind: str, ident: str) -> dict[str, Any]:
    return json.loads((artifact_folder(work / store, kind, ident) / "result.json").read_text(encoding="utf-8"))


def page_of(work: Path, store: str, kind: str, ident: str, name: str | None = None) -> Path:
    base = pages_of(work / store) / kind
    return base / ident / name if name else base / f"{ident}.html"


# ---------- TF18-1 ----------


def test_tf18_1_the_saved_verdicts_are_the_design_sessions(ids: dict[str, tuple[str, str, str]]) -> None:
    for label, ident in MOCKUP_IDS.items():
        assert ids[label][2] == ident, label


@pytest.mark.parametrize("store", ["store", "tables"])
def test_tf18_1_each_store_has_its_pages_and_nothing_more(built: Path, store: str) -> None:
    root = built / store
    assert files_under(pages_of(root)) == expected_files(root)
    assert sorted(os.listdir(ui_root(root))) == ["trace"]


def test_tf18_1_every_kind_has_its_pages(built: Path) -> None:
    got = artifacts(built / "store")
    assert [k for k in KINDS if got[k]] == list(KINDS)
    assert len(got["where"]) == 2


def test_tf18_1_no_page_for_proves_own_comparison(built: Path) -> None:
    assert (built / "store" / ".poisson" / "artifacts" / "comparison" / PROVE_COMPARISON).is_dir()
    for path in pages_of(built / "store").rglob("*.html"):
        assert PROVE_COMPARISON not in path.read_text(encoding="utf-8"), path


# ---------- TF18-2 ----------


def _runs(work: Path, *argv: str) -> tuple[str, dict[str, Any]]:
    plain = cli(work, ["runs", *argv])
    doc = cli(work, ["runs", *argv, "--json"])
    assert plain.code == 0 and doc.code == 0, plain.text
    return plain.out.splitlines()[0], json.loads(doc.out)


def _tool(run: dict[str, Any]) -> str:
    backend = str(run.get("backend") or "")
    return backend[len("import:"):] if backend.startswith("import:") else str(run["target_id"])


def _run_row(run: dict[str, Any]) -> str:
    failed = "–" if run["failed"] is None else f"{run['failed']:,}"
    cells = [str(run["number"]), run["name"], run["run_id"], _tool(run), f"{run['rows']:,}", failed,
             "yes" if run["traced"] else "no", run["created_at"], run["status"]]
    return " | ".join(cells)


@pytest.mark.parametrize("store,argv", [("store", ["--config", "conf/trace.toml"]), ("tables", ["--store", "tables"])])
def test_tf18_2_the_runs_page_opens_with_the_runs_verdict_line(built: Path, store: str, argv: list[str]) -> None:
    line, _doc = _runs(built, *argv)
    page = read_file(pages_of(built / store) / "index.html")
    assert page.h1 == line
    assert page.title == "Runs · poisson-trace"


@pytest.mark.parametrize("store,argv", [("store", ["--config", "conf/trace.toml"]), ("tables", ["--store", "tables"])])
def test_tf18_2_a_row_a_run(built: Path, store: str, argv: list[str]) -> None:
    _line, doc = _runs(built, *argv)
    page = read_file(pages_of(built / store) / "index.html")
    assert "# | name | id | target or tool | rows | failed | traces | started | status" in page.blocks
    rows = [b for b, t in zip(page.blocks, page.block_tags, strict=True) if t == "tr"]
    for run in doc["runs"]:
        assert _run_row(run) in rows, (_run_row(run), rows)


def _saved_rows(work: Path, store: str) -> list[tuple[str, list[str]]]:
    out = []
    for kind, idents in artifacts(work / store).items():
        for ident in idents:
            folder = artifact_folder(work / store, kind, ident)
            art = json.loads((folder / "artifact.json").read_text(encoding="utf-8"))
            res = json.loads((folder / "result.json").read_text(encoding="utf-8"))
            names = [r["run_name"] for r in res["runs"].values()] if kind != "where" else [res["run"]["run_name"]]
            out.append((art["created_at"], [kind, " → ".join(names), res["verdict"], res["sentence"], ident[:12], art["created_at"]]))
    return out


@pytest.mark.parametrize("store", ["store", "tables"])
def test_tf18_2_a_row_a_saved_verdict_newest_first_each_linking_its_page(built: Path, store: str) -> None:
    page = read_file(pages_of(built / store) / "index.html")
    assert "kind | runs | verdict | sentence | id | saved" in page.blocks
    rows = [b for b, t in zip(page.blocks, page.block_tags, strict=True) if t == "tr"]
    want = _saved_rows(built, store)
    at = {" | ".join(cells): rows.index(" | ".join(cells)) for _when, cells in want if " | ".join(cells) in rows}
    assert len(at) == len(want), ([" | ".join(c) for _w, c in want], rows)
    for (when_a, cells_a) in want:
        for (when_b, cells_b) in want:
            if when_a > when_b:
                assert at[" | ".join(cells_a)] < at[" | ".join(cells_b)]
    hrefs = page.hrefs()
    for kind, idents in artifacts(built / store).items():
        for ident in idents:
            assert f"{kind}/{ident}.html" in hrefs


def test_tf18_2_newest_first_on_distinct_save_times(built: Path, tmp_path: Path) -> None:
    """The workspace saves its verdicts within a second or two, so the order is held here on save
    times set apart (an artifact's descriptor is not among the files it lists)."""
    work = copy_work(built, tmp_path)
    folders = [artifact_folder(work / "store", k, i) for k, ids in artifacts(work / "store").items() for i in ids]
    # the save times in an order that is neither the kinds' nor the ids'
    for n, folder in enumerate(sorted(folders, key=lambda f: f.name[::-1])):
        path = folder / "artifact.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["created_at"] = f"2026-11-0{n + 1}T12:00:00Z"
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    assert ui(work, "--config", "conf/trace.toml").code == 0
    page = read_file(pages_of(work / "store") / "index.html")
    want = [cells for _when, cells in sorted(_saved_rows(work, "store"), key=lambda r: r[0], reverse=True)]
    rows = [b for b, t in zip(page.blocks, page.block_tags, strict=True) if t == "tr"]
    got = [r for r in rows if r in {" | ".join(c) for c in want}]
    assert got == [" | ".join(c) for c in want]


def test_tf18_2_a_runs_name_links_its_newest_where_page(built: Path, ids: dict[str, tuple[str, str, str]]) -> None:
    page = read_file(pages_of(built / "store") / "index.html")
    for label, run in (("where after", "agent after"), ("where before", "agent before")):
        target = f"where/{ids[label][2]}.html"
        assert any(e.tag == "a" and e.attrs.get("href") == target and e.text == run for e in page.elements), label


def test_tf18_2_a_run_with_no_saved_where_has_no_link(built: Path) -> None:
    page = read_file(pages_of(built / "tables") / "index.html")
    assert not any(e.tag == "a" and e.text in ("old", "new") for e in page.elements)


# ---------- TF18-3 ----------

VERDICTS = [label for label in SAVES]


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_3_the_first_heading_is_the_verdict_line(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident))
    res = result_of(built, store, kind, ident)
    assert page.h1 == verdict_line(res)
    facts = {e.attrs["data-fact"]: json.loads(e.attrs["data-value"]) for e in page.elements if "data-fact" in e.attrs and "data-value" in e.attrs}
    assert facts.get("/verdict") == res["verdict"] and facts.get("/sentence") == res["sentence"]


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_3_the_title_is_the_reports(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident))
    report = (artifact_folder(built / store, kind, ident) / "report.md").read_text(encoding="utf-8")
    assert page.title == title_line(report)


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_3_every_line_of_the_saved_report_in_order(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident))
    report = (artifact_folder(built / store, kind, ident) / "report.md").read_text(encoding="utf-8")
    assert missing_lines(page, report_lines(report)) == []


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_3_every_line_the_command_prints_with_its_measures(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    ran = cli(built, measures_argv(SAVES[label][1]))
    assert ran.code == 0, ran.text
    lines = report_lines(ran.out)
    page = read_file(page_of(built, store, kind, ident))
    assert missing_lines(page, lines) == []


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_3_the_reports_headings_in_the_reports_order(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    ran = cli(built, measures_argv(SAVES[label][1]))
    want = [line[3:] for line in ran.out.splitlines() if line.startswith("## ")]
    got = read_file(page_of(built, store, kind, ident)).headings()
    it = iter(got)
    assert all(any(h == g for g in it) for h in want), (want, got)


def test_tf18_3_the_fixtures_reach_every_section_the_brief_names(built: Path) -> None:
    fix = cli(built, measures_argv(SAVES["fix-check"][1])).out
    tables = cli(built, measures_argv(SAVES["fix-check tables"][1])).out
    for heading in ("## Failures by kind", "## Time, length, tokens and cost", "## Inputs that changed", "## What it could not have detected"):
        assert heading in fix.splitlines(), heading
    assert "Signals seen on tries, failed or not:" in fix
    assert any(line.startswith("Tries with no outcome: ") for line in tables.splitlines())
    for label in ("compare", "changes"):
        assert "## Failures by kind" in cli(built, SAVES[label][1]).out.splitlines(), label


@pytest.mark.parametrize("label", ["fix-check", "changes", "fix-check tables", "changes tables"])
def test_tf18_3_the_per_input_table_sorts_and_filters(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident))
    out = cli(built, SAVES[label][1]).out.splitlines()
    first = out[out.index("## Inputs that changed"):]
    header = next(line for line in first if line.startswith("|"))
    row = first[first.index(header) + 2]
    sortable = [e for e in page.elements if e.tag == "table" and "data-sort" in e.attrs and e.attrs.get("id")]
    filters = {e.attrs.get("data-filter") for e in page.elements if e.tag == "input" and "filter" in e.attrs.get("class", "").split()}
    holding = [t for t in sortable if missing_lines(page.inside(t.attrs["id"]), [header, row]) == []]
    assert holding, (header, row)
    assert holding[0].attrs["id"] in filters


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_3_what_was_saved(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident))
    art = json.loads((artifact_folder(built / store, kind, ident) / "artifact.json").read_text(encoding="utf-8"))
    text = " ".join(page.blocks)
    assert f".poisson/artifacts/{kind}/{ident}" in text
    for entry in art["files"]:
        assert entry["path"].split("/")[-1] in text, entry["path"]


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_3_links_to_its_could_not_say_page_and_the_runs(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident))
    assert f"{ident}/could-not-say.html" in page.hrefs()
    assert "../index.html" in page.hrefs()


# ---------- TF18-4 ----------


def _data_rows(page: Any) -> list[str]:
    return [b for b, t in zip(page.blocks, page.block_tags, strict=True) if t == "tr"]


@pytest.mark.parametrize("label", ["where after", "where before"])
def test_tf18_4_the_where_curve_inline_with_its_data(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident))
    res = result_of(built, store, kind, ident)
    fig = page.inside("curve")
    assert fig.all("svg"), "no inline chart"
    titles = [e for e in fig.all("title")]
    assert len(titles) >= len(res["curve"])
    rows = _data_rows(fig)
    steps = [r.split(" | ")[0] for r in rows]
    assert [s for s in steps if s.isdigit()] == [str(p["step"]) for p in res["curve"]]
    svg = fig.source
    assert not any(c in svg.lower() for c in MEANING_COLOURS) and not any(c in svg for c in MEANING_CLASSES)


# ---------- TF18-5 ----------

CHARTS = ("charts/curves.svg", "charts/curves.json", "charts/hazard-ratio.svg", "charts/hazard-ratio.json")


def test_tf18_5_the_compare_artifact_carries_its_two_charts(built: Path, ids: dict[str, tuple[str, str, str]]) -> None:
    import hashlib

    store, kind, ident = ids["compare"]
    folder = artifact_folder(built / store, kind, ident)
    art = json.loads((folder / "artifact.json").read_text(encoding="utf-8"))
    listed = {e["path"]: e for e in art["files"]}
    for name in CHARTS:
        assert name in listed, name
        assert listed[name]["sha256"] == hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if name.endswith(".svg"):
            # as TF6 lists where's curve: the SVG a chart, its data beside it a table of the chart format
            assert listed[name]["role"] == "chart" and listed[name]["data"] == name.replace(".svg", ".json")
        else:
            assert listed[name]["role"] == "table" and listed[name]["schema"] == "poisson-trace.chart/1"


def test_tf18_5_the_curves_are_each_runs_where_curve(built: Path, ids: dict[str, tuple[str, str, str]]) -> None:
    store, kind, ident = ids["compare"]
    folder = artifact_folder(built / store, kind, ident)
    doc = json.loads((folder / "charts" / "curves.json").read_text(encoding="utf-8"))
    art = json.loads((folder / "artifact.json").read_text(encoding="utf-8"))
    assert doc["schema"] == "poisson-trace.chart/1"
    assert [r["arm"] for r in doc["runs"]] == ["a", "b"]
    assert [r["run_id"] for r in doc["runs"]] == art["inputs"]["runs"]
    for r, run in zip(doc["runs"], ("agent before", "agent after"), strict=True):
        where = cli(built, ["where", run, "--store", "store", *EV, "--json"])
        assert r["curve"] == json.loads(where.out)["curve"], run


def test_tf18_5_the_hazard_ratio_chart_is_the_verdicts(built: Path, ids: dict[str, tuple[str, str, str]]) -> None:
    store, kind, ident = ids["compare"]
    folder = artifact_folder(built / store, kind, ident)
    doc = json.loads((folder / "charts" / "hazard-ratio.json").read_text(encoding="utf-8"))
    comparison = result_of(built, store, kind, ident)["comparison"]
    assert doc["schema"] == "poisson-trace.chart/1"
    for key in ("hazard_ratio", "hazard_ratio_lo", "hazard_ratio_hi", "mde_hazard_ratio", "max_mde_hr"):
        assert doc[key] == comparison[key], key


def test_tf18_5_the_curves_on_the_page(built: Path, ids: dict[str, tuple[str, str, str]]) -> None:
    store, kind, ident = ids["compare"]
    page = read_file(page_of(built, store, kind, ident))
    doc = json.loads((artifact_folder(built / store, kind, ident) / "charts" / "curves.json").read_text(encoding="utf-8"))
    fig = page.inside("curves")
    assert fig.all("svg")
    classes = [set(e.attrs.get("class", "").split()) for e in fig.elements]
    assert any("before" in c for c in classes) and any("after" in c for c in classes)
    bands = [c for c in classes if any("band" in x for x in c)]
    assert len(bands) >= 2
    texts = [e.text for e in fig.all("text")]
    assert any("agent before" in t for t in texts) and any("agent after" in t for t in texts)
    n = sum(len(r["curve"]) for r in doc["runs"])
    steps = {p["step"] for r in doc["runs"] for p in r["curve"]}
    assert len(fig.all("title")) >= n
    rows = [r for r in _data_rows(fig) if r.split(" | ")[0].strip()]
    assert len(rows) - 1 in (n, len(steps)), rows
    assert not any(c in fig.source.lower() for c in MEANING_COLOURS) and not any(c in fig.source for c in MEANING_CLASSES)


def test_tf18_5_the_hazard_ratio_on_the_page(built: Path, ids: dict[str, tuple[str, str, str]]) -> None:
    store, kind, ident = ids["compare"]
    page = read_file(page_of(built, store, kind, ident))
    fig = page.inside("hazard-ratio")
    assert fig.all("svg") and fig.all("table")
    assert fig.all("title")
    assert not any(c in fig.source.lower() for c in MEANING_COLOURS) and not any(c in fig.source for c in MEANING_CLASSES)


def test_tf18_5_a_compare_bundle_with_its_charts_holds_what_it_promises(built: Path, tmp_path: Path) -> None:
    work = copy_work(built, tmp_path)
    made = cli(work, [*SAVES["compare"][1], "--out", "cb"])
    assert made.code == 0, made.text
    for name in CHARTS:
        assert (work / "cb" / name).is_file(), name
    checked = cli(work, ["handover", "--check", "cb"])
    assert checked.code == 0 and checked.out.startswith("ok  "), checked.text


# ---------- TF18-6 ----------


@pytest.mark.parametrize("label", VERDICTS)
def test_tf18_6_the_could_not_say_page(built: Path, ids: dict[str, tuple[str, str, str]], label: str) -> None:
    store, kind, ident = ids[label]
    page = read_file(page_of(built, store, kind, ident, "could-not-say.html"))
    res = result_of(built, store, kind, ident)
    assert page.h1 == verdict_line(res)
    assert res["cannot_say"], label
    assert missing_lines(page, [f"- {s}" for s in res["cannot_say"]]) == []
    report = cli(built, SAVES[label][1]).out.splitlines()
    if "## What it could not have detected" in report:
        start = report.index("## What it could not have detected")
        end = next(i for i in range(start + 1, len(report)) if report[i].startswith("## "))
        part = [line for line in report[start:end] if line.strip()]
        assert missing_lines(page, part) == []
    assert f"../{ident}.html" in page.hrefs()
    assert page.footer == f"Built by poisson-trace from the store. Nothing was loaded from the network. Address: trace/{kind}/{ident}/could-not-say.html"


# ---------- TF18-7 ----------


def test_tf18_7_each_stores_runs_page_links_the_others(built: Path) -> None:
    for here, there in (("store", "tables"), ("tables", "store")):
        index = pages_of(built / here) / "index.html"
        page = read_file(index)
        targets = [resolve(index, h) for h in page.hrefs() if not h.startswith("#")]
        assert (pages_of(built / there) / "index.html").resolve() in [t.resolve() for t in targets if t], here


def test_tf18_7_no_link_to_another_store_without_a_config(built: Path, tmp_path: Path) -> None:
    work = copy_work(built, tmp_path)
    import shutil

    shutil.rmtree(ui_root(work / "store"))
    ran = ui(work, "--store", "store")
    assert ran.code == 0, ran.text
    index = pages_of(work / "store") / "index.html"
    for h in read_file(index).hrefs():
        if h.startswith("#"):
            continue
        target = resolve(index, h)
        assert target is not None and pages_of(work / "store").resolve() in target.resolve().parents, h


def _prove_ui(store: Path) -> None:
    exe = Path(sys.executable).with_name("poisson-prove")
    ran = subprocess.run([str(exe), "ui", "--store", str(store)], capture_output=True, text=True, timeout=600)
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_tf18_7_a_link_to_proves_dashboard_when_it_is_there(built: Path, tmp_path: Path) -> None:
    work = copy_work(built, tmp_path)
    index = pages_of(work / "store") / "index.html"
    prove = (ui_root(work / "store") / "index.html").resolve()
    before = [resolve(index, h) for h in read_file(index).hrefs() if not h.startswith("#")]
    assert prove not in [t.resolve() for t in before if t]
    _prove_ui(work / "store")
    ran = ui(work, "--config", "conf/trace.toml")
    assert ran.code == 0, ran.text
    page = read_file(index)
    assert "../index.html" in page.hrefs()
